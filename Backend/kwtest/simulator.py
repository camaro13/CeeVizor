# simulator.py
import json, re
from typing import List, Dict, Any
from kwgdb import trace_c_execution, gdb_print, gdb_x
from tree_parser import analyze_c_code

HEX_PTR_RE = re.compile(r"^0x[0-9a-fA-F]+$")

def to_number_or_keep(v: str):
    v = v.strip()
    if (len(v) >= 2 and v[0]=='"' and v[-1]=='"') or (len(v) >= 3 and v[:2]=='L"' and v[-1]=='"'):
        return v
    if HEX_PTR_RE.match(v): return v
    v = re.sub(r"^\([^)]*\)\s*", "", v)
    try:
        if v.lower().startswith("0x"): return int(v, 16)
        if re.match(r"^-?\d+$", v): return int(v)
        if re.match(r"^-?\d+\.\d+$", v): return float(v)
    except: pass
    return v

def globals_from_symbols(symbols: List[Dict[str, Any]]) -> List[str]:
    names = []
    for s in symbols:
        if s.get("type") == "function": continue
        if s.get("scope") == "global" or s.get("location") in ("data","bss"):
            names.append(s["name"])
    return sorted(set(names))

def function_decl_map(code: str) -> Dict[str, Dict[str, Any]]:
    lines = code.splitlines()
    info = {}
    for s in analyze_c_code(code):
        if s.get("type") == "function":
            ln = s.get("line", 0)
            txt = lines[ln-1].rstrip() if 1 <= ln <= len(lines) else (s["name"] + "()")
            info[s["name"]] = {"line": ln, "text": txt, "params": {p["name"] for p in (s.get("parameters") or [])}}
    return info

def local_decl_lines_and_ptrs(code: str):
    decl_lines: Dict[str, Dict[str,int]] = {}
    ptr_locals: Dict[str, set] = {}
    for s in analyze_c_code(code):
        if s.get("type") == "function": continue
        if s.get("location") == "stack" and s.get("scope") and s.get("name"):
            func = s["scope"]; var = s["name"]; ln = int(s.get("line", 0) or 0)
            decl_lines.setdefault(func, {})[var] = ln
            if s.get("pointer"):  # tree-sitter가 알려줌
                ptr_locals.setdefault(func, set()).add(var)
    return decl_lines, ptr_locals

def read_global_numbers(globals_list: List[str]) -> Dict[str, int]:
    ds = {}
    for name in globals_list:
        out = gdb_print(name)
        m = re.search(r"=\s*(-?\d+)", out)
        ds[name] = int(m.group(1)) if m else 0
    return ds

def gdb_read_var(name: str):
    out = gdb_print(name)
    m = re.search(r"=\s*(.+)$", out.strip())
    if not m: return None
    return to_number_or_keep(m.group(1).strip())

def extract_ptrs_from_frame(frame: Dict[str, Any]) -> Dict[str,str]:
    ptrs = {}
    for k, v in frame.get("variables", {}).items():
        if isinstance(v, str) and HEX_PTR_RE.match(v):
            ptrs[k] = v
    return ptrs

def gdb_peek_int(addr: str):
    out = gdb_x(addr, "wd")
    m = re.search(rf"{re.escape(addr)}:\s*(-?\d+)", out)
    return int(m.group(1)) if m else None

def heap_state_from_map(addr_values: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [{addr: addr_values[addr]} for addr in sorted(addr_values.keys())]

# --- 선언 줄 상수 초기화 파싱 (간단한 숫자 리터럴만) ---
# 예: "int x = 3, y = 4;" → {"x": 3, "y": 4}
DECL_INIT_NUM_RE = re.compile(
    r'\b([_a-zA-Z]\w*)\s*=\s*([+-]?(?:0x[0-9a-fA-F]+|\d+(?:\.\d+)?))'
)

WRITE_DEREF_RE = re.compile(r'\*(\w+)\s*=')
MALLOC_DECL_RE  = re.compile(r'\b(?:\w+\s*\*+\s*)?(\w+)\s*=\s*\([^)]*\)\s*malloc\s*\(')
MALLOC_DECL_SIMPLE = re.compile(r'\b(\w+)\s*=\s*malloc\s*\(')

def detect_heap_writes(code_line: str, ptr_vars: Dict[str,str]) -> List[str]:
    written = set()
    if code_line:
        m = WRITE_DEREF_RE.search(code_line)
        if m:
            var = m.group(1)
            addr = ptr_vars.get(var)
            if addr: written.add(addr)
        if "memset" in code_line or "memcpy" in code_line:
            for name, addr in ptr_vars.items():
                if re.search(rf'\b{name}\b', code_line):
                    written.add(addr)
    return sorted(written)

def sanitize_bt_stack(bt_funcs: List[str], user_funcs: set, prev_stack: List[Dict[str,Any]]) -> List[str]:
    res, seen = [], set()
    for f in bt_funcs:
        if not f or f.startswith("0x"): continue
        if f in user_funcs or f == "main":
            if f not in seen:
                seen.add(f); res.append(f)
    if not res and prev_stack:
        res = [fr.get("function") for fr in prev_stack if fr.get("function")]
    return res

def accumulate_output(prev: str, program_chunk: str) -> str:
    if not program_chunk: return prev
    lines = []
    for line in program_chunk.splitlines():
        s = line.strip()
        if not s: continue
        if s.startswith("(gdb)") or s.startswith("Frame ") or s.startswith("Breakpoint ") or s.startswith("#"):
            continue
        if s in ("No locals.", "No arguments."):
            continue
        lines.append(line)
    if not lines: return prev
    return prev + ("\n".join(lines).rstrip() + "\n")

def build_timeline(code: str, max_steps: int = 200, include_func_decls: bool = True) -> List[Dict[str, Any]]:
    symbols = analyze_c_code(code)
    globals_list = globals_from_symbols(symbols)
    func_meta = function_decl_map(code)
    user_funcs = set(func_meta.keys())
    decl_lines, ptr_locals = local_decl_lines_and_ptrs(code)

    traced = trace_c_execution(code, return_result=True, max_steps=max_steps)
    steps:  List[Dict[str, Any]] = traced["steps"]

    timeline: List[Dict[str, Any]] = [{
        "time": 0,
        "line_index": 0,
        "line": "프로그램 시작 및 전역변수 초기화",
        "memory": { "data_segment": read_global_numbers(globals_list), "heap": [], "stack": [] },
        "output": ""
    }]

    heap_values: Dict[str, Any] = {}   # addr → (None | int)
    pending_writes: set[str] = set()
    pending_ptr_captures: Dict[str, str] = {}  # {func: varname} malloc 라인에서 못잡은 포인터
    output_accum = ""
    stack_state: List[Dict[str, Any]] = []
    time_counter = 1
    seen_decl = set()

    for st in steps:
        bt_funcs = sanitize_bt_stack(st.get("bt_funcs", []) or [], user_funcs, stack_state)
        top_func = bt_funcs[0] if bt_funcs else None

        # 함수 선언 스냅샷
        if include_func_decls and top_func and top_func not in seen_decl and top_func in func_meta:
            finfo = func_meta[top_func]
            preview_stack = stack_state[:] + [{ "function": top_func, "variables": {} }]
            timeline.append({
                "time": time_counter,
                "line_index": finfo["line"],
                "line": finfo["text"],
                "memory": {
                    "data_segment": read_global_numbers(globals_list),
                    "heap": heap_state_from_map(heap_values),
                    "stack": preview_stack
                },
                "output": output_accum
            })
            time_counter += 1
            seen_decl.add(top_func)

        # ---- 1) GDB locals/args + 선언 라인 규칙
        fixed_vars: Dict[str, Any] = {}
        current_vars_raw = st.get("vars") or {}
        cur_ln = st.get("line_no") or 0
        params = func_meta.get(top_func, {}).get("params", set())
        for k, v in current_vars_raw.items():
            if k not in params:
                dln = decl_lines.get(top_func, {}).get(k)
                if dln is None or cur_ln < dln:
                    continue
                if cur_ln == dln:
                    fixed_vars[k] = None  # 기본은 null
                    continue
            if isinstance(v, str) and "optimized out" in v:
                vv = gdb_read_var(k)
                if vv is not None: v = vv
            fixed_vars[k] = to_number_or_keep(v)

        # ---- 1-보강) 선언 라인의 숫자 리터럴 초기화는 즉시 값 채우기
        code_line = st.get("code_line") or ""
        if top_func and cur_ln in (decl_lines.get(top_func, {}).values() or []):
            for name, val in DECL_INIT_NUM_RE.findall(code_line):
                if name in decl_lines.get(top_func, {}):
                    # 선언 라인에서 바로 값 보여주기
                    if HEX_PTR_RE.match(val):
                        parsed = int(val, 16)
                    elif re.match(r"^[+-]?\d+\.\d+$", val):
                        parsed = float(val)
                    elif re.match(r"^[+-]?\d+$", val):
                        parsed = int(val)
                    else:
                        parsed = None
                    fixed_vars[name] = parsed

        # ---- 2) Tree-sitter 기반 빠진 로컬 백필 (특히 포인터)
        declared = decl_lines.get(top_func, {}) if top_func else {}
        for var, dln in declared.items():
            if cur_ln < dln:  # 아직 선언 전
                continue
            if var in fixed_vars:
                continue
            if cur_ln == dln:
                # 선언 라인이지만 리터럴이 아니면 null 유지
                fixed_vars[var] = fixed_vars.get(var, None)
                continue
            vv = gdb_read_var(var)
            if vv is not None:
                fixed_vars[var] = vv

        # 스택 재구성
        if bt_funcs:
            stack_state = []
            for idx, f in enumerate(bt_funcs):
                stack_state.append({ "function": f, "variables": fixed_vars if idx == 0 else {} })

        # ---- 3) malloc 줄 보정 + 포인터 주소 지연 캡처
        if "malloc" in code_line and top_func:
            m = MALLOC_DECL_RE.search(code_line) or MALLOC_DECL_SIMPLE.search(code_line)
            if m:
                varname = m.group(1)
                if varname in declared and cur_ln >= declared[varname]:
                    vv = gdb_read_var(varname)
                    if isinstance(vv, str) and HEX_PTR_RE.match(vv):
                        if stack_state:
                            stack_state[0]["variables"][varname] = vv
                        if vv not in heap_values:
                            heap_values[vv] = None
                    else:
                        # 지금 못 잡았으면 다음 스텝부터 계속 시도
                        pending_ptr_captures[top_func] = varname

        # (다음 스텝들에서) 보류된 포인터 주소 캡처 재시도
        if top_func and top_func in pending_ptr_captures:
            varname = pending_ptr_captures[top_func]
            vv = gdb_read_var(varname)
            if isinstance(vv, str) and HEX_PTR_RE.match(vv):
                if stack_state:
                    stack_state[0]["variables"][varname] = vv
                if vv not in heap_values:
                    heap_values[vv] = None
                del pending_ptr_captures[top_func]

        # 포인터 변수에서 주소 수집 (스택 값 기준)
        top_frame = stack_state[0] if stack_state else {"variables": {}}
        ptr_vars = extract_ptrs_from_frame(top_frame)
        for addr in ptr_vars.values():
            if addr not in heap_values:
                heap_values[addr] = None

        # ---- 4) 쓰기 감지: ptr_vars에 없더라도 var 이름으로 강제 조회(fallback)
        written_now = set(detect_heap_writes(code_line, ptr_vars))
        mwrite = WRITE_DEREF_RE.search(code_line or "")
        if mwrite and top_func:
            varname = mwrite.group(1)
            if varname not in ptr_vars:
                vv = gdb_read_var(varname)
                if isinstance(vv, str) and HEX_PTR_RE.match(vv):
                    if stack_state:
                        stack_state[0]["variables"][varname] = vv
                    if vv not in heap_values:
                        heap_values[vv] = None
                    written_now.add(vv)

        # pending 주소 값 읽기
        pending_writes.update(written_now)
        for addr in list(pending_writes):
            val = gdb_peek_int(addr)
            if val is not None:
                heap_values[addr] = val
                pending_writes.discard(addr)

        # 스텝 스냅샷
        snapshot = {
            "time": time_counter,
            "line_index": cur_ln,
            "line": code_line,
            "memory": {
                "data_segment": read_global_numbers(globals_list),
                "heap": heap_state_from_map(heap_values),
                "stack": stack_state[:]
            },
            "output": accumulate_output(output_accum, st.get("program_chunk") or "")
        }
        output_accum = snapshot["output"]
        timeline.append(snapshot)
        time_counter += 1

    return timeline

if __name__ == "__main__":
    sample_code = r'''
#include <stdio.h>
#include <stdlib.h>

int g = 10;
static int s = 20;

int add(int a, int b) {
    int sum = a + b;
    printf("add=%d\n", sum);
    return sum;
}

int main(void) {
    setvbuf(stdout, NULL, _IONBF, 0);
    int x = 3, y = 4;
    int *p = (int*)malloc(sizeof(int));
    *p = add(x, y);
    printf("p=%d\n", *p);
    free(p);
    return 0;
}
'''
    tl = build_timeline(sample_code, max_steps=200, include_func_decls=True)
    print(json.dumps(tl, ensure_ascii=False, indent=2))
