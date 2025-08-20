from __future__ import annotations
import os, re, json
from datetime import datetime
from contextlib import contextmanager
from typing import List, Dict, Any, Optional

from tree_parser import analyze_c_code
from run_gdb import (
    save_code_to_file,
    compile_code,
    calc_executable_lines,
    run_gdb,
    parse_gdb_output_linebps,
    run_program_and_capture_stdout,
    split_print_calls,
)

@contextmanager
def pushd(path: str):
    old = os.getcwd()
    os.makedirs(path, exist_ok=True)
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)

def make_run_dir(base: str = "workspace", name: Optional[str] = None) -> str:
    if name is None:
        name = "run_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    out = os.path.join(base, name)
    os.makedirs(out, exist_ok=True)
    return out

_NUM_LIT = re.compile(r"^\s*(-?(?:0[xX][0-9a-fA-F]+|\d+))\s*$")
_EMPTY_SENTINELS = {"<uninitialized>", "<optimized out>", "(nil)", "N/A", "?"}

SYNTH_ADDR_BASE = 0x55550000
SYNTH_ADDR_STEP = 0x10
_alloc_seq = 0

def _normalize_nulls_for_display(vars_dict: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for k, v in (vars_dict or {}).items():
        if v is None:
            out[k] = "NULL"
            continue
        s = str(v).strip()
        if (s == "") or (s in _EMPTY_SENTINELS) or (s == "0x0"):
            out[k] = "NULL"
        else:
            out[k] = v
    return out

DECL_LINE_RE = re.compile(
    r'^\s*'
    r'(?:static\s+|const\s+|volatile\s+|register\s+)*'
    r'(?:(?:unsigned|signed)\s+)?'
    r'(?:(?:long\s+long|long|short)\s+)?'
    r'(?:int|char|float|double|bool)\s+'
    r'(.+?)\s*;'
)
def _parse_inline_decl(line: str) -> dict[str, Optional[str]]:
    # for (int i=0; ... ) 의 init 추출
    m_for = re.search(r'\bfor\s*\(([^)]*)\)', line)
    if m_for:
        first_seg = m_for.group(1).split(';', 1)[0].strip()
        if first_seg:
            line = first_seg + ';'
    m = DECL_LINE_RE.match(line)
    if not m:
        return {}
    tail = m.group(1)
    out: dict[str, Optional[str]] = {}
    NUM_LIT  = re.compile(r'^\s*(?:-?(?:0[xX][0-9a-fA-F]+|\d+))\s*$')
    CHAR_LIT = re.compile(r"^\s*'(?:\\.|[^\\'])'\s*$")
    for part in [p.strip() for p in tail.split(",") if p.strip()]:
        clean = re.sub(r'\([^)]*\)', ' ', part)
        clean = re.sub(r'\[[^\]]*\]', ' ', clean).replace('*', ' ')
        if '=' in clean:
            left, right = clean.split('=', 1)
            tokens = [t for t in re.split(r'\s+', left.strip()) if t]
            name = tokens[-1] if tokens else None
            val_raw = right.strip()
            if NUM_LIT.match(val_raw) or CHAR_LIT.match(val_raw):
                val = val_raw
            else:
                val = None
        else:
            tokens = [t for t in re.split(r'\s+', clean.strip()) if t]
            name = tokens[-1] if tokens else None  # <- 오타 수정
            val = None
        if name and re.match(r'^[A-Za-z_]\w*$', name):
            out[name] = val
    return out

def _to_int_if_possible(v: Optional[str]):
    if v is None:
        return None
    m = _NUM_LIT.match(v)
    if not m:
        return v
    s = m.group(1)
    try:
        return int(s, 16) if s.lower().startswith("0x") else int(s, 10)
    except:
        return v

def _strip_comments(code: str) -> str:
    code = re.sub(r'/\*.*?\*/', '', code, flags=re.S)
    code = re.sub(r'//.*', '', code)
    return code

def _fallback_scan_top_globals(code: str) -> list[tuple[str, bool]]:
    code = _strip_comments(code)
    decls: list[tuple[str, bool]] = []
    buf = []
    depth = 0
    for ch in code:
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth = max(depth - 1, 0)
        if depth == 0:
            buf.append(ch)
            if ch == ';':
                stmt = ''.join(buf).strip()
                buf = []
                if stmt.startswith(('typedef', 'extern', 'struct', 'union', 'enum')):
                    continue
                if re.search(r'\b[A-Za-z_]\w*\s*\(', stmt) and not re.search(r'\(\s*\*', stmt):
                    continue
                m = re.match(
                    r'^\s*(?:static\s+)?(?:(?:unsigned|signed)\s+)?'
                    r'(?:(?:long\s+long|long|short)\s+)?'
                    r'(?:int|char|float|double|bool)\s+(.+?);$',
                    stmt
                )
                if not m:
                    continue
                tail = m.group(1)
                for part in (p.strip() for p in tail.split(',') if p.strip()):
                    has_init = '=' in part
                    left = part.split('=', 1)[0].strip()
                    left = re.sub(r'\([^)]*\)', ' ', left)
                    left = re.sub(r'\[[^\]]*\]', ' ', left)
                    left = left.replace('*', ' ')
                    tokens = [t for t in re.split(r'\s+', left) if t]
                    if not tokens:
                        continue
                    name = tokens[-1]
                    if re.match(r'^[A-Za-z_]\w*$', name):
                        decls.append((name, has_init))
    return decls

def get_initial_memory(code: str) -> Dict[str, Any]:
    symbols = analyze_c_code(code)
    data_segment: Dict[str, Any] = {}
    for s in symbols:
        if s.get("kind") != "var":
            continue
        scope = s.get("scope", {}) or {}
        storage = s.get("storage", "auto")
        location = s.get("location", "")
        name = s.get("name")
        val = s.get("value")
        if not name:
            continue
        is_global = scope.get("kind") == "global"
        is_func_static = (scope.get("kind") == "function") and (storage == "static")
        if not (is_global or is_func_static):
            continue
        if location == "data":
            data_segment[name] = _to_int_if_possible(val) if val is not None else 0
        elif location == "bss":
            data_segment[name] = 0
        else:
            data_segment[name] = _to_int_if_possible(val) if val is not None else 0
    for name, _has_init in _fallback_scan_top_globals(code):
        if name not in data_segment:
            data_segment[name] = 0
    return {"data_segment": data_segment, "heap": [], "stack": []}

def build_decl_map_from_treesitter(code: str) -> Dict[str, Dict[str, int]]:
    symbols = analyze_c_code(code)
    m: Dict[str, Dict[str, int]] = {}
    for s in symbols:
        if s.get("kind") != "var":
            continue
        scope = s.get("scope", {}) or {}
        if scope.get("kind") != "function":
            continue
        func = scope.get("func")
        name = s.get("name")
        ln = int(s.get("line", 0))
        if func and name:
            m.setdefault(func, {})[name] = ln
    return m

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

def build_params_map_from_treesitter(code: str) -> Dict[str, List[str]]:
    params: Dict[str, List[str]] = {}
    for s in analyze_c_code(code):
        if s.get("kind") != "param":
            continue
        scope = s.get("scope", {}) or {}
        func = scope.get("func")
        name = s.get("name")
        if func and name:
            params.setdefault(func, []).append(name)
    return params

def build_params_map_from_source(code: str) -> Dict[str, List[str]]:
    code_nc = re.sub(r'/\*.*?\*/', '', code, flags=re.S)
    code_nc = re.sub(r'//.*', '', code_nc)
    pat = re.compile(r'\b([A-Za-z_]\w*)\s*\(([^)]*)\)\s*\{', re.S)
    out: Dict[str, List[str]] = {}
    for m in pat.finditer(code_nc):
        fn = m.group(1)
        params = m.group(2).strip()
        if params == "" or params == "void":
            out[fn] = []
            continue
        names: List[str] = []
        for p in params.split(','):
            p = p.strip()
            p = p.split('=')[0].strip()
            tokens = [t for t in re.split(r'\s+', p.replace('*', ' ')) if t]
            if tokens:
                cand = tokens[-1]
                if re.match(r'^[A-Za-z_]\w*$', cand):
                    names.append(cand)
        out[fn] = names
    return out

def _addr_from_val(v: Any) -> Optional[str]:
    """문자열 '0x..' 또는 정수 주소값을 모두 안전하게 주소로 변환."""
    if isinstance(v, str):
        m = re.search(r"0x[0-9a-fA-F]+", v)
        if not m:
            return None
        a = m.group(0).lower()
        return None if a == "0x0" else a
    if isinstance(v, int):
        if v == 0:
            return None
        # 정수는 포인터 컨텍스트(역참조/heap ptr에서만)에서 사용되므로 그대로 주소로 취급
        return f"0x{v:x}"
    return None

def _decorate_ptrs_for_display(fn: str, vars_raw: Dict[str, Any], heap_map: Dict[str, Any], heap_ptrs: Dict[str, set]) -> Dict[str, Any]:
    out = dict(vars_raw)
    for ptr in heap_ptrs.get(fn, set()):
        v = out.get(ptr)
        s = str(v).strip() if v is not None else ""
        is_empty = (v is None) or (s == "") or (s in _EMPTY_SENTINELS) or (s == "0x0") or (s.upper() == "NULL")
        addr = _addr_from_val(v)
        key = addr if addr else f"heap:{ptr}"
        if is_empty and key:
            out[ptr] = f"<{key}>"
    return out

def simulate_c_code_to_timeline(
    code: str,
    out_dir: Optional[str] = None,
    out_json_name: str = "timeline.json",
    source_file_name: str = "main.c",
    binary_name: Optional[str] = None,
    save_json: bool = True,
    dump_gdb: bool = False,
) -> List[Dict[str, Any]]:
    IDENT = re.compile(r'^[A-Za-z_]\w*$')

    # 간단 evaluator: 정수/식별자/+, - 만
    def _eval_simple(expr: str, env: Dict[str, Any]) -> Optional[int]:
        s = (expr or "").strip()
        if re.fullmatch(r'-?(?:0[xX][0-9a-fA-F]+|\d+)', s):
            try:
                return int(s, 0)
            except:
                return None
        parts = re.split(r'(\+|\-)', s)
        total, sign = 0, 1
        for t in parts:
            t = t.strip()
            if t == '+': sign = 1; continue
            if t == '-': sign = -1; continue
            if not t: continue
            if re.fullmatch(r'-?(?:0[xX][0-9a-fA-F]+|\d+)', t):
                val = int(t, 0)
            elif IDENT.match(t):
                raw = env.get(t)
                if raw is None: return None
                try:
                    val = int(raw, 0) if isinstance(raw, str) else int(raw)
                except:
                    return None
            else:
                return None
            total += sign * val
        return total

    def _intify(v):
        if isinstance(v, str) and re.fullmatch(r'-?(?:0[xX][0-9a-fA-F]+|\d+)', v.strip()):
            try: return int(v, 0)
            except: return v
        return v

    # 전역 갱신 감지
    ASSIGN_RE = re.compile(r'^\s*([A-Za-z_]\w*)\s*=\s*([^;]+);')
    ADDEQ_RE  = re.compile(r'^\s*([A-Za-z_]\w*)\s*\+=\s*([^;]+);')
    SUBEQ_RE  = re.compile(r'^\s*([A-Za-z_]\w*)\s*-=\s*([^;]+);')
    INC_RE    = re.compile(r'(?:\+\+\s*([A-Za-z_]\w*)|([A-Za-z_]\w*)\s*\+\+)')
    DEC_RE    = re.compile(r'(?:--\s*([A-Za-z_]\w*)|([A-Za-z_]\w*)\s*--)')

    # 호출/리턴 전파
    CALL_WITH_ARGS_RE = re.compile(
        r'^\s*(?:[A-Za-z_]\w*(?:\s*\*+)?\s+)?([A-Za-z_]\w*)\s*=\s*([A-Za-z_]\w*)\s*\(([^)]*)\)\s*;')
    CALL_NOASSIGN_RE  = re.compile(r'^\s*([A-Za-z_]\w*)\s*\(([^)]*)\)\s*;')
    RETURN_RE         = re.compile(r'^\s*return\s+(.+?)\s*;')

    # 전역 char 배열의 문자열 초기값 (예: char msg[20] = "Hello";)
    STRING_INIT_RE = re.compile(r'\bchar\s+([A-Za-z_]\w*)\s*\[\s*[^\]]*\s*\]\s*=\s*"([^"]*)"')

    run_dir = out_dir or make_run_dir("workspace")
    bin_name = binary_name or ("a.exe" if os.name == "nt" else "a.out")

    with pushd(run_dir):
        save_code_to_file(code, filename=source_file_name)
        ok = bool(compile_code(source_file=source_file_name, output_file=bin_name))
        if not ok:
            raise RuntimeError("컴파일 실패")

        exec_lines, _ = calc_executable_lines(source_file_name)

        # 타입 맵 구성 (Tree-sitter 결과 + char 배열 보정)
        symbols = analyze_c_code(code) or []
        GLOBAL_TYPES = {
            s["name"]: (s.get("type") or "int")
            for s in symbols
            if s.get("kind") == "var" and (s.get("scope") or {}).get("kind") == "global"
        }
        # char 배열: char name[dim] → char[dim]
        for nm, dim in re.findall(r'\bchar\s+([A-Za-z_]\w*)\s*\[([^\]]*)\]', code):
            dim = dim.strip()
            GLOBAL_TYPES[nm] = f"char[{dim or '?'}]"

        FUNC_VAR_TYPES = {
            ((s.get("scope") or {}).get("func"), s["name"]): (s.get("type") or "int")
            for s in symbols
            if s.get("kind") == "var" and (s.get("scope") or {}).get("kind") == "function"
        }
        PARAM_NAMES = build_params_map_from_source(code)  # 이름만이라도 확보

        def _var_type(fn: Optional[str], name: str) -> str:
            return (
                FUNC_VAR_TYPES.get((fn, name))
                or GLOBAL_TYPES.get(name)
                or "int"
            )

        decl_map_ts = build_decl_map_from_treesitter(code)

        try:
            gdb_output = run_gdb(binary=bin_name, exec_lines=exec_lines, source_file=source_file_name)
        except TypeError:
            gdb_output = run_gdb(exec_lines=exec_lines, source_file=source_file_name)

        if dump_gdb:
            with open("gdb_raw.txt", "w", encoding="utf-8") as f:
                f.write(gdb_output)

        executed_lines, executed_code, frames = parse_gdb_output_linebps(gdb_output, source_file_name)

        try:
            stdout_lines = run_program_and_capture_stdout(bin_name)
        except TypeError:
            stdout_lines = run_program_and_capture_stdout(binary=bin_name)

        # 초기 전역 메모리(배열/중복키 정리 + 문자열 초기값 반영)
        initial_mem = get_initial_memory(code)
        globals_env: Dict[str, Any] = {}

        # 1) base 이름으로 통합 (msg[20] → msg)
        for k, v in (initial_mem.get("data_segment") or {}).items():
            base = k.split("[", 1)[0] if "[" in k else k
            if isinstance(v, str) and len(v) >= 2 and v[0] == v[-1] == '"':
                v = v[1:-1]  # "Hello" → Hello
            globals_env.setdefault(base, v)

        # 2) 선언만 있고 빠진 전역은 0으로 채움
        for name in list(GLOBAL_TYPES.keys()):
            globals_env.setdefault(name, 0)

        # 3) char 배열의 문자열 초기값 덮어쓰기
        for nm, s in STRING_INIT_RE.findall(code):
            globals_env[nm] = s

        def _data_snapshot_typed() -> Dict[str, Any]:
            # 브래킷 이름(msg[20])은 숨김
            snap = {}
            for name, val in globals_env.items():
                if "[" in name:
                    continue
                snap[name] = {"type": GLOBAL_TYPES.get(name, "int"), "value": val}
            return snap

        timeline: List[Dict[str, Any]] = [{
            "time": 0,
            "line_index": 0,
            "line": "프로그램 시작 및 전역변수 초기화",
            "memory": {"data_segment": _data_snapshot_typed(), "heap": [], "stack": []},
            "output": ""
        }]

        last_vars_by_func: Dict[str, Dict[str, Any]] = {}
        pending_calls: Dict[str, List[Dict[str, Any]]] = {}  # { callee: [ {caller, target, raw_args, param_names, env} ] }

        for i, (ln, code_line, frame) in enumerate(zip(executed_lines, executed_code, frames), start=1):
            fn = frame.get("func", "main")
            args_raw = frame.get("args") or {}
            locals_raw = frame.get("locals") or {}

            # 선언 전 로컬 숨김
            filtered_locals: Dict[str, Any] = {}
            fn_decl_map = decl_map_ts.get(fn, {})
            for name, val in locals_raw.items():
                dln = fn_decl_map.get(name)
                if dln is None or ln > dln:
                    filtered_locals[name] = val

            # ---- 호출 인자/대입 타겟 기록 ----
            m_call = CALL_WITH_ARGS_RE.match(code_line)
            if m_call:
                target, callee, argstr = m_call.groups()
                raw_args = [t.strip() for t in argstr.split(",") if t.strip()]
                pnames = PARAM_NAMES.get(callee) or []
                caller_env = {**globals_env, **(last_vars_by_func.get(fn, {}) or {}), **args_raw, **filtered_locals}
                info = {"caller": fn, "target": target, "raw_args": raw_args, "param_names": pnames, "env": caller_env}
                pending_calls.setdefault(callee, []).append(info)

                # ★ 대입 대상 placeholder 생성 (호출 직후부터 보이게)
                prev = last_vars_by_func.get(fn, {}) or {}
                if target not in prev:
                    prev[target] = None
                last_vars_by_func[fn] = prev

            m_call2 = CALL_NOASSIGN_RE.match(code_line)
            if m_call2 and not m_call:
                callee, argstr = m_call2.groups()
                raw_args = [t.strip() for t in argstr.split(",") if t.strip()]
                pnames = PARAM_NAMES.get(callee) or []
                caller_env = {**globals_env, **(last_vars_by_func.get(fn, {}) or {}), **args_raw, **filtered_locals}
                info = {"caller": fn, "target": None, "raw_args": raw_args, "param_names": pnames, "env": caller_env}
                pending_calls.setdefault(callee, []).append(info)
            # ---------------------------------

            # 이 프레임이 callee라면, 저장해둔 호출자 환경으로 인자 값 선주입
            if pending_calls.get(fn):
                top = pending_calls[fn][-1]
                merged_pre = {**args_raw, **filtered_locals}
                for idx, name in enumerate(top["param_names"]):
                    if name and name not in merged_pre:
                        val = None
                        if idx < len(top["raw_args"]):
                            val = _eval_simple(top["raw_args"][idx], top["env"])
                        merged_pre[name] = val
            else:
                merged_pre = {**args_raw, **filtered_locals}

            # 인라인 선언 보정: 리터럴만 덮어쓰기, 그 외는 GDB 값 유지
            decl_inline = _parse_inline_decl(code_line)
            if decl_inline:
                for nm in decl_inline.keys():
                    merged_pre.pop(nm, None)

                # 1) 숫자/문자 리터럴
                for nm, val in decl_inline.items():
                    if val is not None:
                        merged_pre[nm] = val
                    else:
                        if nm in locals_raw:
                            merged_pre[nm] = locals_raw[nm]

                # 2) int lhs = r1 * r2; (r1,r2는 식별자 또는 정수)
                m_mul = re.match(
                    r'.*\b([A-Za-z_]\w*)\s*=\s*([A-Za-z_]\w*|-?(?:0[xX][0-9a-fA-F]+|\d+))\s*\*\s*([A-Za-z_]\w*|-?(?:0[xX][0-9a-fA-F]+|\d+))\s*;',
                    code_line
                )
                if m_mul:
                    lhs, r1, r2 = m_mul.groups()
                    if lhs in decl_inline and lhs not in merged_pre:
                        def _get(v):
                            if re.fullmatch(r'-?(?:0[xX][0-9a-fA-F]+|\d+)', v): return int(v, 0)
                            return merged_pre.get(v)
                        v1, v2 = _get(r1), _get(r2)
                        try:
                            if v1 is not None and v2 is not None:
                                v1 = int(v1, 0) if isinstance(v1, str) else int(v1)
                                v2 = int(v2, 0) if isinstance(v2, str) else int(v2)
                                merged_pre[lhs] = v1 * v2
                        except Exception:
                            pass

                # 3) char* p = msg;  (글로벌 char 배열을 가리키는 포인터)
                m_ptr = re.match(r'^\s*char\s*\*\s*([A-Za-z_]\w*)\s*=\s*([A-Za-z_]\w*)\s*;', code_line)
                if m_ptr:
                    lhs, rhs = m_ptr.groups()
                    if lhs in decl_inline and lhs not in merged_pre:
                        if (GLOBAL_TYPES.get(rhs) or "").startswith("char["):
                            merged_pre[lhs] = f"&{rhs}[0]"

            merged = merged_pre

            # ===== 전역 변수 갱신 (data_segment 실시간 반영) =====
            env_for_eval = {**globals_env, **merged}

            m = ASSIGN_RE.match(code_line)
            if m and (m.group(1) in globals_env):
                name, rhs = m.group(1), m.group(2)
                val = _eval_simple(rhs, env_for_eval)
                if val is not None:
                    globals_env[name] = val

            for g in INC_RE.findall(code_line):
                name = g[0] or g[1]
                if name in globals_env:
                    try: globals_env[name] = int(globals_env.get(name, 0)) + 1
                    except: pass

            for g in DEC_RE.findall(code_line):
                name = g[0] or g[1]
                if name in globals_env:
                    try: globals_env[name] = int(globals_env.get(name, 0)) - 1
                    except: pass

            m = ADDEQ_RE.match(code_line)
            if m and (m.group(1) in globals_env):
                name, rhs = m.group(1), m.group(2)
                delta = _eval_simple(rhs, env_for_eval)
                if delta is not None:
                    try: globals_env[name] = int(globals_env.get(name, 0)) + int(delta)
                    except: pass

            m = SUBEQ_RE.match(code_line)
            if m and (m.group(1) in globals_env):
                name, rhs = m.group(1), m.group(2)
                delta = _eval_simple(rhs, env_for_eval)
                if delta is not None:
                    try: globals_env[name] = int(globals_env.get(name, 0)) - int(delta)
                    except: pass
            # =====================================================

            # ===== return 전파 (호출자 환경으로 결과 반영) =====
            m_ret = RETURN_RE.match(code_line)
            if m_ret and pending_calls.get(fn):
                rv = m_ret.group(1)
                # ★ 여기서 env에 '이전 프레임 캐시(last_vars_by_func[fn])'도 합쳐서 product 등을 안정적으로 읽음
                rval = _eval_simple(rv, {**globals_env, **(last_vars_by_func.get(fn, {}) or {}), **merged})
                top = pending_calls[fn].pop()
                if top["target"]:
                    caller = top["caller"]; var = top["target"]
                    prev = last_vars_by_func.get(caller, {}) or {}
                    prev[var] = rval  # None 허용(그래도 보이게)
                    last_vars_by_func[caller] = prev
            # =====================================================

            # 콜스택(현재 함수가 맨 위로 오게)
            cs = frame.get("callstack")
            if cs and isinstance(cs[0], dict):
                stack_funcs = [d.get("func", "?") for d in cs]
            elif cs and isinstance(cs[0], str):
                stack_funcs = list(cs)
            else:
                stack_funcs = [fn]
            stack_funcs = [fn] + [s for s in stack_funcs if s != fn]

            # 표시용 스택(타입/숫자 캐스팅 포함)
            # ★ 현재 함수는 merged가 None인 값으로 캐시를 덮어쓰지 않도록 병합
            base_self = dict(last_vars_by_func.get(fn, {}) or {})
            for k, v in merged.items():
                if v is not None:
                    base_self[k] = v
            stack_entries = []
            for sfn in stack_funcs:
                if sfn == fn:
                    vars_for_fn = base_self
                else:
                    vars_for_fn = (last_vars_by_func.get(sfn, {}) or {})
                typed_vars = {
                    k: {"type": _var_type(sfn, k), "value": _intify(v)}
                    for k, v in vars_for_fn.items()
                    if not (isinstance(k, str) and k.startswith('*'))
                }
                stack_entries.append({"function": sfn, "variables": typed_vars})

            # 캐시 업데이트(캐시는 그대로 merged 반영 — None도 저장 가능)
            if merged:
                last_vars_by_func[fn] = {**(last_vars_by_func.get(fn, {}) or {}), **merged}
            elif fn not in last_vars_by_func:
                last_vars_by_func[fn] = {}

            mem_state = {
                "data_segment": _data_snapshot_typed(),
                "heap": [],  # (이 예제는 heap 미사용. 필요 시 기존 heap 추적 로직 연결)
                "stack": stack_entries
            }

            timeline.append({
                "time": i,
                "line_index": ln,
                "line": code_line,
                "memory": mem_state,
                "output": ""
            })

        # stdout 매핑
        _attach_stdout_to_timeline(timeline, stdout_lines)

        if save_json:
            with open(out_json_name, "w", encoding="utf-8") as f:
                json.dump(timeline, f, ensure_ascii=False, indent=2)

    return timeline
