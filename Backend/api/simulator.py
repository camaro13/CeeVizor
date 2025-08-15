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

    def _is_empty_slot(val: Any) -> bool:
        if val is None:
            return True
        s = str(val).strip()
        return (s == "") or (s in _EMPTY_SENTINELS) or (s == "0x0") or (s.upper() == "NULL")

    pending_args_pos: Dict[str, List[List[Optional[int]]]] = {}
    last_vars_by_func: Dict[str, Dict[str, Any]] = {}

    def _read_int(token: Any, merged: Dict[str, Any], cache_fn: str, last_vars: Dict[str, Dict[str, Any]]) -> Optional[int]:
        s = str(token).strip() if token is not None else ""
        if _NUM_LIT.match(s):
            try:
                return int(s, 0)
            except:
                return None
        v = merged.get(s)
        if v is None:
            v = (last_vars.get(cache_fn, {}) or {}).get(s)
        if v is not None:
            try:
                return int(v, 0) if isinstance(v, str) else int(v)
            except:
                return None
        pos_stack = pending_args_pos.get(cache_fn)
        if pos_stack and len(pos_stack) > 0:
            top = pos_stack[-1]
            if len(top) == 1 and top[0] is not None:
                try:
                    return int(top[0])
                except:
                    return None
        return None

    run_dir = out_dir or make_run_dir("workspace")
    bin_name = binary_name or ("a.exe" if os.name == "nt" else "a.out")

    with pushd(run_dir):
        save_code_to_file(code, filename=source_file_name)
        ret = compile_code(source_file=source_file_name, output_file=bin_name)
        ok = ret[0] if isinstance(ret, (list, tuple)) else bool(ret)
        if not ok:
            raise RuntimeError("컴파일 실패")

        exec_lines, _ = calc_executable_lines(source_file_name)
        decl_map_ts   = build_decl_map_from_treesitter(code)
        params_by_fn  = build_params_map_from_treesitter(code)

        # 파라미터 폴백(소스 파싱으로 이름만이라도 확보)
        params_fallback = build_params_map_from_source(code)
        for fn, names in params_fallback.items():
            if not params_by_fn.get(fn):
                params_by_fn[fn] = names

        initial_mem   = get_initial_memory(code)
        globals_env   = dict(initial_mem.get("data_segment", {}))
        init_map      = _initializers_map(code)

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

        timeline: List[Dict[str, Any]] = [{
            "time": 0,
            "line_index": 0,
            "line": "프로그램 시작 및 전역변수 초기화",
            "memory": initial_mem,
            "output": ""
        }]

        heap_map: Dict[str, Any] = {}
        heap_ptrs: Dict[str, set] = {}
        last_vars_by_func = {}
        pending_ret: Dict[str, List[Dict[str, str]]] = {}
        pending_argmap: Dict[str, List[Dict[str, Optional[int]]]] = {}
        pending_args_pos = {}
        last_for_key_by_func: Dict[str, tuple] = {}
        loop_iters: Dict[tuple, Dict[str, int]] = {}
        last_body_ln_by_func: Dict[str, int] = {}
        alloc_seq = 0

        def _eval_expr_simple(expr: str, env: Dict[str, Any]) -> Optional[int]:
            parts = re.split(r'(\+|\-)', expr)
            total, sign = 0, 1
            for t in parts:
                t = t.strip()
                if t == '+':
                    sign = 1; continue
                if t == '-':
                    sign = -1; continue
                if not t:
                    continue
                if _NUM_LIT.match(t):
                    val = int(t, 0)
                elif IDENT.match(t):
                    raw = env.get(t)
                    if raw is None:
                        raw = globals_env.get(t)
                    if raw is None:
                        return None
                    val = int(raw, 0) if isinstance(raw, str) else int(raw)
                else:
                    return None
                total += sign * val
            return total

        # malloc에서만 새 주소 생성(create=True). 그 외엔 create=False로 주소 재사용.
        def _heap_key_for(ptr_name: str, merged: Dict[str, Any], func: str, create: bool=False) -> Optional[str]:
            nonlocal alloc_seq
            cur = merged.get(ptr_name)
            if cur is None:
                cur = (last_vars_by_func.get(func, {}) or {}).get(ptr_name)
            addr = _addr_from_val(cur)
            if addr:
                return addr
            if not create:
                return None
            if ptr_name not in (heap_ptrs.get(func) or set()):
                return None
            alloc_seq += 1
            addr_int = SYNTH_ADDR_BASE + alloc_seq * SYNTH_ADDR_STEP
            key = f"0x{addr_int:08x}"
            merged[ptr_name] = key
            last_vars_by_func[func] = {**(last_vars_by_func.get(func, {}) or {}), ptr_name: key}
            return key

        # 정규식들
        DEREF_INIT_RE     = re.compile(r'^\s*(?:int|char|float|double|bool)\s+([A-Za-z_]\w*)\s*=\s*\*([A-Za-z_]\w*)\s*;')
        ASSIGN_STAR_STAR  = re.compile(r'^\s*\*([A-Za-z_]\w*)\s*=\s*\*([A-Za-z_]\w*)\s*;')
        ASSIGN_STAR_VAL   = re.compile(r'^\s*\*([A-Za-z_]\w*)\s*=\s*([^;]+)\s*;')
        DEREF_SUM_ASSIGN  = re.compile(r'^\s*(?:int\s+)?([A-Za-z_]\w*)\s*=\s*\*([A-Za-z_]\w*)\s*\+\s*\*([A-Za-z_]\w*)\s*;')
        CALL_WITH_ARGS_RE = re.compile(r'^\s*(?:int\s+)?([A-Za-z_]\w*)\s*=\s*([A-Za-z_]\w*)\s*\(([^)]*)\)\s*;')
        CALL_NOASSIGN_RE  = re.compile(r'^\s*([A-Za-z_]\w*)\s*\(([^)]*)\)\s*;')
        RETURN_RE         = re.compile(r'^\s*return\s+([A-Za-z_]\w*|-?(?:0[xX][0-9a-fA-F]+|\d+))\s*;')
        FOR_HEADER_RE     = re.compile(r'^\s*for\s*\(\s*(?:int\s+)?([A-Za-z_]\w*)\s*=\s*([0-9]+)\s*;')
        ACCUM_RE          = re.compile(r'^\s*([A-Za-z_]\w*)\s*\+=\s*\*([A-Za-z_]\w*)\s*\+\s*([A-Za-z_]\w*)\s*;')
        MALLOC_ASSIGN_RE  = re.compile(r'^\s*(?:[A-Za-z_]\w*(?:\s*\*+)?\s+)?([A-Za-z_]\w*)\s*=\s*.*\bmalloc\s*\(')
        FREE_CALL_RE      = re.compile(r'\s*free\s*\(\s*([A-Za-z_]\w*)\s*\)\s*;')

        for i, (ln, code_line, frame) in enumerate(zip(executed_lines, executed_code, frames), start=1):
            f = frame.get("func", "main")
            args = frame.get("args") or {}
            locals_raw = frame.get("locals") or {}

            # 선언 라인 이후의 로컬만 노출
            filtered_locals: Dict[str, Any] = {}
            fn_decl_map = decl_map_ts.get(f, {})
            for name, val in locals_raw.items():
                dln = fn_decl_map.get(name)
                if dln is None or ln > dln:
                    filtered_locals[name] = val

            # 한 줄 선언(for의 init 포함) 보정
            decl_inline = _parse_inline_decl(code_line)
            if decl_inline:
                for nm in decl_inline.keys():
                    filtered_locals.pop(nm, None)
                for nm, val in decl_inline.items():
                    filtered_locals[nm] = val if val is not None else None

            # treesitter가 잡은 초기화값 보정
            for k, v in (init_map.get((f, ln), {}) or {}).items():
                filtered_locals[k] = v

            merged: Dict[str, Any] = {**args, **filtered_locals}

            # 스택 함수 목록
            cs = frame.get("callstack")
            if cs:
                stack_funcs = [d.get("func", "?") for d in cs] if isinstance(cs[0], dict) else list(cs)
            else:
                st = frame.get("stack")
                stack_funcs = [s if isinstance(s, str) else str(s) for s in (st or [f])]

            caller_fn = stack_funcs[-2] if len(stack_funcs) >= 2 else None
            caller_cache = last_vars_by_func.get(caller_fn, {}) if caller_fn else {}

            # 대입 있는 호출로 전달된 인자 → 피호출자 프레임 준비
            m_call = CALL_WITH_ARGS_RE.match(code_line)
            if m_call:
                target_var, callee_name, argstr = m_call.groups()
                env_base = {**(last_vars_by_func.get(f, {}) or {}), **merged}
                arg_vals: List[Optional[int]] = []
                arg_texts = [x.strip() for x in argstr.split(',') if x.strip()]
                for raw in arg_texts:
                    arg_vals.append(_eval_expr_simple(raw, env_base))
                names = params_by_fn.get(callee_name, [])
                amap: Dict[str, Optional[int]] = {}
                for idx, val in enumerate(arg_vals):
                    if idx < len(names):
                        amap[names[idx]] = val
                pending_argmap.setdefault(callee_name, []).append(amap)
                pending_args_pos.setdefault(callee_name, []).append(arg_vals)
                pending_ret.setdefault(callee_name, []).append({'caller': f, 'var': target_var})

            # 대입 없는 호출도 인자 추적 (오타 수정: dict 호출 제거)
            m_call2 = CALL_NOASSIGN_RE.match(code_line)
            if m_call2 and not m_call:
                callee_name, argstr = m_call2.groups()
                env_base = {**(last_vars_by_func.get(f, {}) or {}), **merged}
                arg_vals: List[Optional[int]] = []
                arg_texts = [x.strip() for x in argstr.split(',') if x.strip()]
                for raw in arg_texts:
                    arg_vals.append(_eval_expr_simple(raw, env_base))
                names = params_by_fn.get(callee_name, [])
                # 인자 이름 → 값 매핑
                amap: Dict[str, Optional[int]] = {}
                for idx, val in enumerate(arg_vals):
                    if idx < len(names):
                        amap[names[idx]] = val
                pending_argmap.setdefault(callee_name, []).append(amap)
                pending_args_pos.setdefault(callee_name, []).append(arg_vals)

            # tmp = *a; (호출자 캐시 역참조 읽기)
            m_deref = DEREF_INIT_RE.match(code_line)
            if m_deref and caller_fn:
                lhs, srcptr = m_deref.groups()
                if srcptr in caller_cache:
                    merged[lhs] = caller_cache[srcptr]

            # *a = *b; (호출자 캐시에 쓰기 반영)
            m_ss = ASSIGN_STAR_STAR.match(code_line)
            if m_ss and caller_fn:
                dstptr, srcptr = m_ss.groups()
                if srcptr in caller_cache:
                    val = caller_cache[srcptr]
                    if val is not None:
                        cc = {**caller_cache, dstptr: val}
                        last_vars_by_func[caller_fn] = cc
                        caller_cache = cc

            # malloc 할당 발견 → 포인터 등록 + 주소 발급
            m_malloc = MALLOC_ASSIGN_RE.match(code_line)
            if m_malloc:
                name = m_malloc.group(1)
                heap_ptrs.setdefault(f, set()).add(name)
                key = _heap_key_for(name, merged, f, create=True)
                if key and key not in heap_map:
                    heap_map[key] = "?"

            # *ptr = expr; (주소 생성 금지, 기존 주소만 사용)
            m_sv = ASSIGN_STAR_VAL.match(code_line)
            if m_sv:
                dstptr, rhs_expr = m_sv.groups()
                key = _heap_key_for(dstptr, merged, f, create=False)
                env_eval = {**(last_vars_by_func.get(f, {}) or {}), **merged}
                val_num = _eval_expr_simple(rhs_expr, env_eval)
                if key and val_num is not None:
                    heap_map[key] = val_num
                if caller_fn and (dstptr in (params_by_fn.get(f, []) or [])):
                    wb_val = _eval_expr_simple(rhs_expr, env_eval)
                    if wb_val is not None:
                        cc = {**caller_cache, dstptr: wb_val}
                        last_vars_by_func[caller_fn] = cc
                        caller_cache = cc

            # free(ptr); (주소 생성 금지, 기존 주소만 제거)
            m_free = FREE_CALL_RE.match(code_line)
            if m_free:
                ptr = m_free.group(1)
                key = _heap_key_for(ptr, merged, f, create=False)
                if key in heap_map:
                    del heap_map[key]

            # acc += *p + i;
            m_acc = ACCUM_RE.match(code_line)
            if m_acc:
                acc_name, p_name, i_name = m_acc.groups()
                p_key = _heap_key_for(p_name, merged, f, create=False)
                p_val = heap_map.get(p_key) if p_key else None
                try:
                    p_val = int(p_val)
                except Exception:
                    p_val = None
                i_val = _read_int(i_name, merged, f, last_vars_by_func)
                acc_prev = _read_int(acc_name, merged, f, last_vars_by_func) or 0
                if p_val is not None and i_val is not None:
                    merged[acc_name] = acc_prev + p_val + i_val

            # r = *p + *q;
            m_sum = DEREF_SUM_ASSIGN.match(code_line)
            if m_sum:
                target, p1, p2 = m_sum.groups()
                k1 = _heap_key_for(p1, merged, f, create=False)
                k2 = _heap_key_for(p2, merged, f, create=False)
                v1 = heap_map.get(k1) if k1 else None
                v2 = heap_map.get(k2) if k2 else None
                try:
                    merged[target] = (int(v1) if v1 is not None else 0) + (int(v2) if v2 is not None else 0)
                except Exception:
                    pass

            # return ...
            m_ret = RETURN_RE.match(code_line)
            if m_ret:
                rv = m_ret.group(1)
                ret_val = _read_int(rv, merged, f, last_vars_by_func)
                if pending_ret.get(f):
                    info = pending_ret[f].pop()
                    caller = info['caller']
                    var = info['var']
                    cc = {**(last_vars_by_func.get(caller, {}) or {})}
                    if ret_val is not None:
                        cc[var] = ret_val
                    last_vars_by_func[caller] = cc
                if pending_argmap.get(f):
                    pending_argmap[f].pop()
                if pending_args_pos.get(f):
                    pending_args_pos[f].pop()

            # 프레임에서 관측된 주소는 힙 테이블에 등록 (문자열/정수 모두 허용)
            for _, v in merged.items():
                addr = _addr_from_val(v)
                if addr and addr not in heap_map:
                    heap_map[addr] = "?"

            # 스택 표시(포인터 역참조 키 제거)
            current_display = {**(last_vars_by_func.get(f, {}) or {}), **merged}
            stack_entries = []
            for fn in stack_funcs:
                if fn == f:
                    vars_for_fn_raw = current_display
                else:
                    vars_for_fn_raw = (last_vars_by_func.get(fn, {}) or {})
                vars_for_fn_raw = _decorate_ptrs_for_display(fn, vars_for_fn_raw, heap_map, heap_ptrs)
                vars_for_fn = {k: v for k, v in vars_for_fn_raw.items() if not (isinstance(k, str) and k.startswith('*'))}
                stack_entries.append({
                    "function": fn,
                    "variables": _normalize_nulls_for_display(vars_for_fn)
                })

            if merged:
                last_vars_by_func[f] = {**(last_vars_by_func.get(f, {}) or {}), **merged}
            elif f not in last_vars_by_func:
                last_vars_by_func[f] = {}

            mem_state = {
                "data_segment": dict(initial_mem["data_segment"]),
                "heap": [{addr: val} for addr, val in heap_map.items()],
                "stack": stack_entries
            }
            timeline.append({
                "time": i,
                "line_index": ln,
                "line": code_line,
                "memory": mem_state,
                "output": ""
            })

        _attach_stdout_to_timeline(timeline, stdout_lines)
        if save_json:
            with open(out_json_name, "w", encoding="utf-8") as f:
                json.dump(timeline, f, ensure_ascii=False, indent=2)

    return timeline

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run simulator and save all outputs to one folder")
    parser.add_argument("--code-file", "-i", type=str, required=True, help="C source file path")
    parser.add_argument("--out-dir", "-o", type=str, default=None, help="Output folder (single run folder)")
    parser.add_argument("--binary-name", type=str, default=None, help="Output binary name (a.exe/a.out default)")
    parser.add_argument("--no-save-json", action="store_true", help="Do not write timeline.json")
    parser.add_argument("--dump-gdb", action="store_true", help="Dump raw gdb output to gdb_raw.txt")
    args = parser.parse_args()

    with open(args.code_file, "r", encoding="utf-8") as f:
        code = f.read()

    timeline = simulate_c_code_to_timeline(
        code,
        out_dir=args.out_dir,
        binary_name=args.binary_name,
        save_json=not args.no_save_json,
        dump_gdb=args.dump_gdb,
    )
    print("[+] timeline length:", len(timeline))
