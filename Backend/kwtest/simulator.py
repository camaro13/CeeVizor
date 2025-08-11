from __future__ import annotations
import os, re, json
from datetime import datetime
from contextlib import contextmanager
from typing import List, Dict, Any, Optional

from tree_parser import analyze_c_code
from kwgdb import (
    save_code_to_file,
    compile_code,
    calc_executable_lines,
    run_gdb,
    parse_gdb_output_linebps,
    run_program_and_capture_stdout,
    split_print_calls,
)

@contextmanager
# 작업 디렉터리를 임시로 변경
def pushd(path: str):
    old = os.getcwd()
    os.makedirs(path, exist_ok=True)
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)

# 실행 폴더 생성(기본: workspace/run_타임스탬프)
def make_run_dir(base: str = "workspace", name: Optional[str] = None) -> str:
    if name is None:
        name = "run_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    out = os.path.join(base, name)
    os.makedirs(out, exist_ok=True)
    return out

_NUM_LIT = re.compile(r"^\s*(-?(?:0[xX][0-9a-fA-F]+|\d+))\s*$")

# 선언 라인의 변수와 초기값을 파싱
DECL_LINE_RE = re.compile(
    r'^\s*'
    r'(?:static\s+|const\s+|volatile\s+|register\s+)*'
    r'(?:(?:unsigned|signed)\s+)?'
    r'(?:(?:long\s+long|long|short)\s+)?'
    r'(?:int|char|float|double|bool)\s+'
    r'(.+?)\s*;'
)

def _parse_inline_decl(line: str) -> dict[str, Optional[str]]:
    m = DECL_LINE_RE.match(line)
    if not m:
        return {}
    tail = m.group(1)
    out: dict[str, Optional[str]] = {}
    for part in [p.strip() for p in tail.split(",") if p.strip()]:
        # 괄호(캐스팅/함수포인터) 제거, 포인터/배열 기호 제거
        clean = re.sub(r'\([^)]*\)', ' ', part)
        clean = re.sub(r'\[[^\]]*\]', ' ', clean).replace('*', ' ')
        if '=' in clean:
            left, right = clean.split('=', 1)
            tokens = [t for t in re.split(r'\s+', left.strip()) if t]
            name = tokens[-1] if tokens else None
            val = right.strip()
        else:
            tokens = [t for t in re.split(r'\s+', clean.strip()) if t]
            name = tokens[-1] if tokens else None
            val = None
        if name and re.match(r'^[A-Za-z_]\w*$', name):
            out[name] = val
    return out


# 숫자 문자열을 int로 변환
def _to_int_if_possible(v: Optional[str]):
    if v is None: return None
    m = _NUM_LIT.match(v)
    if not m: return v
    s = m.group(1)
    try: return int(s, 16) if s.lower().startswith("0x") else int(s, 10)
    except: return v

# Tree-sitter 결과로 초기 메모리 구성(time=0)
def get_initial_memory(code: str) -> Dict[str, Any]:
    symbols = analyze_c_code(code)
    data_segment: Dict[str, Any] = {}
    for s in symbols:
        if s.get("kind") != "var": continue
        scope = s.get("scope", {}) or {}
        storage = s.get("storage", "auto")
        location = s.get("location", "")
        name = s.get("name"); val = s.get("value")
        is_global = scope.get("kind") == "global"
        is_func_static = (scope.get("kind") == "function") and (storage == "static")
        if is_global or is_func_static:
            if location == "data":
                data_segment[name] = _to_int_if_possible(val)
            elif location == "bss":
                data_segment[name] = 0
            else:
                data_segment[name] = _to_int_if_possible(val) if val is not None else 0
    return {"data_segment": data_segment, "heap": [], "stack": []}

# Tree-sitter로 함수별 선언 라인 맵 구성
def build_decl_map_from_treesitter(code: str) -> Dict[str, Dict[str, int]]:
    symbols = analyze_c_code(code)
    m: Dict[str, Dict[str, int]] = {}
    for s in symbols:
        if s.get("kind") != "var": continue
        scope = s.get("scope", {}) or {}
        if scope.get("kind") != "function": continue
        func = scope.get("func"); name = s.get("name"); ln = int(s.get("line", 0))
        if func and name: m.setdefault(func, {})[name] = ln
    return m

# 선언 라인의 초기화 값 맵 생성(선언 라인에 깔끔한 값 노출)
def _initializers_map(code: str) -> Dict[tuple, Dict[str, Any]]:
    m: Dict[tuple, Dict[str, Any]] = {}
    for s in analyze_c_code(code):
        if s.get("kind") != "var":
            continue
        sc = s.get("scope", {}) or {}
        if sc.get("kind") == "function" and s.get("value") is not None:
            fn = sc.get("func")
            ln = int(s.get("line", 0))
            m.setdefault((fn, ln), {})[s["name"]] = s["value"]
    return m

# stdout 토큰을 타임라인 스냅샷에 매핑
def _attach_stdout_to_timeline(timeline: List[Dict[str, Any]], stdout_lines: List[str]) -> None:
    pending_owner_idx = None
    for i, snap in enumerate(timeline):
        for (_func, has_nl) in split_print_calls(snap["line"]):
            if has_nl:
                token = stdout_lines.pop(0) if stdout_lines else ""
                owner = pending_owner_idx if pending_owner_idx is not None else i
                timeline[owner]["output"] += token
                pending_owner_idx = None
            else:
                pending_owner_idx = i

HEX_ADDR = re.compile(r"0x[0-9a-fA-F]+")
ASSIGN_DEREF_INT = re.compile(r'\s*\*\s*([A-Za-z_]\w*)\s*=\s*([0-9]+)\s*;')
FREE_CALL = re.compile(r'\s*free\s*\(\s*([A-Za-z_]\w*)\s*\)\s*;')

# 로컬 값 문자열에서 포인터 주소 추출
def _addr_from_val(v: str) -> Optional[str]:
    if not isinstance(v, str): return None
    m = HEX_ADDR.search(v)
    if not m: return None
    addr = m.group(0)
    return None if addr == "0x0" else addr

# 로컬 변수들에서 포인터 주소를 힙에 등록
def _sync_heap_from_locals(heap_map: Dict[str, Any], locals_vars: Dict[str, str]) -> None:
    for _, v in locals_vars.items():
        addr = _addr_from_val(v)
        if addr and addr not in heap_map:
            heap_map[addr] = "?"

# 코드 라인 힌트로 힙 값 갱신/해제
def _apply_heap_hints(code_line: str, locals_vars: Dict[str, str], heap_map: Dict[str, Any]) -> None:
    m = ASSIGN_DEREF_INT.match(code_line)
    if m:
        ptr, sval = m.group(1), m.group(2)
        addr = _addr_from_val(locals_vars.get(ptr, ""))
        if addr: heap_map[addr] = int(sval)
        return
    m = FREE_CALL.match(code_line)
    if m:
        ptr = m.group(1)
        addr = _addr_from_val(locals_vars.get(ptr, ""))
        if addr and addr in heap_map: del heap_map[addr]

# C 코드를 시뮬레이션해 실행 타임라인 생성
def simulate_c_code_to_timeline(
    code: str,
    out_dir: Optional[str] = None,
    out_json_name: str = "timeline.json",
    source_file_name: str = "main.c",
    binary_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    run_dir = out_dir or make_run_dir("workspace")
    bin_name = binary_name or ("a.exe" if os.name == "nt" else "a.out")

    with pushd(run_dir):
        save_code_to_file(code, filename=source_file_name)
        ret = compile_code(source_file=source_file_name, output_file=bin_name)
        ok = ret[0] if isinstance(ret, (list, tuple)) else bool(ret)
        if not ok:
            raise RuntimeError("컴파일 실패")

        exec_lines, _ = calc_executable_lines(source_file_name)
        decl_map = build_decl_map_from_treesitter(code)
        initial_mem = get_initial_memory(code)
        init_map = _initializers_map(code)

        try:
            gdb_output = run_gdb(binary=bin_name, exec_lines=exec_lines, source_file=source_file_name)
        except TypeError:
            gdb_output = run_gdb(exec_lines=exec_lines, source_file=source_file_name)

        with open("gdb_raw.txt", "w", encoding="utf-8") as f:
            f.write(gdb_output)

        executed_lines, executed_code, frames = parse_gdb_output_linebps(gdb_output, source_file_name)

        try:
            stdout_lines = run_program_and_capture_stdout(bin_name)
        except TypeError:
            stdout_lines = run_program_and_capture_stdout(binary=bin_name)

        timeline: List[Dict[str, Any]] = [{
            "time": 0,
            "line_index": 0,
            "line": "프로그램 시작 및 전역변수 초기화",
            "memory": initial_mem,
            "output": ""
        }]

        heap_map: Dict[str, Any] = {}
        for i, (ln, code_line, frame) in enumerate(zip(executed_lines, executed_code, frames), start=1):
            f = frame.get("func", "main")
            args = frame.get("args") or {}
            locals_raw = frame.get("locals") or {}

            filtered_locals: Dict[str, str] = {}
            fn_decl_map = decl_map.get(f, {})
            for name, val in locals_raw.items():
                dln = fn_decl_map.get(name)
                if dln is None or ln > dln:
                    filtered_locals[name] = val
                                # 선언 라인에서 쓰레기값 제거 + 초기값 덮어쓰기
            decl_inline = _parse_inline_decl(code_line)
            if decl_inline:
                # 2-1) 쓰레기값 제거(이 줄에서 선언된 변수는 GDB값 무시)
                for nm in decl_inline.keys():
                    if nm in filtered_locals:
                        del filtered_locals[nm]
                # 2-2) 초기값 있으면 해당 값으로 세팅
                for nm, val in decl_inline.items():
                    if val is not None:
                        filtered_locals[nm] = val


            init_vals = init_map.get((f, ln), {})
            for k, v in init_vals.items():
                filtered_locals[k] = v

            merged = {**args, **filtered_locals}
            _sync_heap_from_locals(heap_map, merged)
            _apply_heap_hints(code_line, merged, heap_map)

            mem_state = {
                "data_segment": dict(initial_mem["data_segment"]),
                "heap": [{addr: val} for addr, val in heap_map.items()],
                "stack": [{
                    "function": f,
                    "variables": merged
                }]
            }

            timeline.append({
                "time": i,
                "line_index": ln,
                "line": code_line,
                "memory": mem_state,
                "output": ""
            })

        _attach_stdout_to_timeline(timeline, stdout_lines)

        with open(out_json_name, "w", encoding="utf-8") as f:
            json.dump(timeline, f, ensure_ascii=False, indent=2)

    return timeline

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run simulator and save all outputs to one folder")
    parser.add_argument("--code-file", "-i", type=str, required=True, help="C source file path")
    parser.add_argument("--out-dir", "-o", type=str, default=None, help="Output folder (single run folder)")
    parser.add_argument("--binary-name", type=str, default=None, help="Output binary name (a.exe/a.out default)")
    args = parser.parse_args()

    with open(args.code_file, "r", encoding="utf-8") as f:
        code = f.read()

    timeline = simulate_c_code_to_timeline(
        code,
        out_dir=args.out_dir,
        binary_name=args.binary_name,
    )
    print("[+] timeline length:", len(timeline))
