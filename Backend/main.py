from fastapi import FastAPI, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from tree_parser import analyze_c_code
import os, shutil, subprocess, json, re, shutil as sh
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# CORS: 리액트 개발서버 도메인 허용 (localhost/127.0.0.1)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000","http://localhost:3001","http://127.0.0.1:3001",],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "workspace")
FILENAME = "main.c"
EXEC_NAME = "a.out"  # ★ WSL/Linux: a.out

FRONTEND_BUILD_DIR = os.path.join(BASE_DIR, "Frontend/build")

app.mount("/static", StaticFiles(directory=os.path.join(FRONTEND_BUILD_DIR, "static")), name="static")

def simulate_execution(code: str):
    lines = code.splitlines()
    timeline = []
    memory = {
        "stack": {},
        "heap": {},
        "data": {},
        "heap_counter": 1
    }
    
    analysis = analyze_c_code(code)

    for time, raw_line in enumerate(lines, start=1):
        relevant_symbols = [s for s in analysis if s.get("line") == time]

        # int x = 5;
        for symbol in relevant_symbols:
            loc = symbol.get("location")
            if loc in ["stack", "heap", "data"]:
                mem = memory[loc]
                mem[symbol["name"]] = {
                    "name": symbol["name"],
                    "type": symbol["type"],
                    "value": symbol.get("value"),
                    "pointer": symbol.get("pointer"),
                    "points_to": symbol.get("points_to"),
                    "scope": symbol.get("scope", "global")
                }

        # 타임라인에 상태 복사
        timeline.append({
            "time": time,
            "line": raw_line,
            "stack": list(memory["stack"].values()),
            "heap": list(memory["heap"].values()),
            "data": list(memory["data"].values()),
        })

    return timeline



def simulate_with_gdb(code: str, exec_path: str, source_path: str):
    try:
        if not sh.which("gdb"):
            raise RuntimeError("gdb not found in PATH")

        code_lines = code.splitlines()
        source_basename = os.path.basename(source_path) if source_path else "main.c"
        analysis = analyze_c_code(code)

        # ---------- helpers ----------
        def _base_name(n: str) -> str:
            i = n.find('[')
            return n[:i] if i != -1 else n

        def clean_value_string(val: str) -> str:
            if val is None:
                return val
            s = str(val).strip()
            # 문자열 리터럴이면 마지막 쿼트만
            qs = re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', s)
            if qs:
                return '"' + qs[-1] + '"'
            # 0x.. <sym>  → &sym 로 정규화
            mtag = re.search(r'<([^>]+)>', s)
            if mtag:
                return f"&{mtag.group(1)}"
            # 순수 주소 토막 제거(남는 게 없으면 이전값 유지 로직이 살려줌)
            s = re.sub(r'^0x[0-9a-fA-F]+\s*(<[^>]+>)?\s*', '', s)
            return s

        def group_by_scope(flat_vars):
            grouped = {}
            for var in flat_vars:
                scope = var.get("scope", "global")
                grouped.setdefault(scope, {})[var["name"]] = var
            return grouped

        def update_memory(prev_list, curr_vars):
            prev_map = {v["name"]: v for v in prev_list}
            out = {}
            for var in curr_vars:
                nm = var["name"]
                newv = var.get("value")
                # 새 값이 비었으면 이전값 유지(값 사라짐 방지)
                if nm in prev_map and (newv is None or newv == "" or newv == []):
                    out[nm] = prev_map[nm]
                    continue
                prevv = prev_map.get(nm, {}).get("value")
                out[nm] = var if prevv != newv else prev_map.get(nm, var)
            for nm, v in prev_map.items():
                if nm not in out:
                    out[nm] = v
            return list(out.values())

        # 선언 줄 초기화 파싱(문자열/괄호 안전)
        def parse_decl_inits_for_line(line_text: str):
            line_text = re.sub(r'//.*$', '', line_text)
            parts, buf, depth = [], [], 0
            in_str, esc = False, False
            for ch in line_text:
                if in_str:
                    buf.append(ch)
                    if esc: esc = False
                    elif ch == '\\': esc = True
                    elif ch == '"': in_str = False
                    continue
                if ch == '"':
                    in_str = True; buf.append(ch); continue
                if ch == '(':
                    depth += 1
                elif ch == ')':
                    depth = max(0, depth - 1)
                if ch == ',' and depth == 0:
                    parts.append(''.join(buf)); buf = []
                else:
                    buf.append(ch)
            if buf: parts.append(''.join(buf))
            init_map = {}
            for p in parts:
                p2 = p.strip().rstrip(';').strip()
                eq = p2.rfind('=')
                if eq == -1: continue
                lhs = p2[:eq].strip()
                rhs = p2[eq+1:].strip()
                m = re.search(r'([A-Za-z_]\w*)\s*$', lhs)
                if not m: continue
                init_map[m.group(1)] = rhs
            return init_map

        # 백트레이스 파서(우리 소스 프레임만)
        bt_frame_full_re = re.compile(r'^#(\d+)\s+([A-Za-z_]\w*)\s*\([^)]*\)\s+at\s+(.+):(\d+)\b')
        def parse_user_frames(bt_lines):
            frames = []
            for ln in bt_lines:
                m = bt_frame_full_re.match(ln.strip())
                if not m: continue
                idx, func, filep, lno = int(m.group(1)), m.group(2), m.group(3), int(m.group(4))
                if os.path.basename(filep) == source_basename:
                    frames.append((idx, func, lno))
            return frames

        def top_user_frame(bt_lines):
            u = parse_user_frames(bt_lines)
            return min(u, key=lambda t: t[0]) if u else None  # (#가 가장 작은 = 현재 유저 프레임)

        def is_loopy(text: str) -> bool:
            return bool(re.search(r'\b(for|while)\s*\(', text) or re.search(r'\bdo\b', text))

        # 포인터 대입 p = &b;
        re_ptr_assign = re.compile(r'\b([A-Za-z_]\w*)\s*=\s*&\s*([A-Za-z_]\w*)\s*;?')

        # printf 캡처
        printf_re = re.compile(r'printf\s*\(\s*"([^"\\]*(?:\\.[^"\\]*)*)"\s*(?:,\s*(.*))?\)\s*;?')
        def split_args(arg_text: str):
            if not arg_text: return []
            args, buf, depth, in_str, esc = [], [], 0, False, False
            for ch in arg_text:
                if in_str:
                    buf.append(ch)
                    if esc: esc = False
                    elif ch == '\\': esc = True
                    elif ch == '"': in_str = False
                    continue
                if ch == '"':
                    in_str = True; buf.append(ch); continue
                if ch == '(':
                    depth += 1; buf.append(ch); continue
                if ch == ')':
                    depth = max(0, depth-1); buf.append(ch); continue
                if ch == ',' and depth == 0:
                    args.append(''.join(buf).strip()); buf = []; continue
                buf.append(ch)
            if buf: args.append(''.join(buf).strip())
            return args
        def unescape_basic(s: str):
            return s.replace(r'\n', '\n').replace(r'\t', '\t').replace(r'\"', '"').replace(r"\\", "\\")
        def to_int(val):
            if val is None: return 0
            s = str(val).strip().strip('"')
            try: return int(s, 0)
            except:
                m = re.search(r'-?\d+', s)
                return int(m.group(0)) if m else 0

        # ---------- 분석 맵 ----------
        scope_map = {sym["name"]: sym.get("scope", "global")
                     for sym in analysis if sym.get("location") in ("stack","heap","data")}
        declared_line_map = {sym["name"]: sym.get("line", 0)
                             for sym in analysis if sym.get("location") in ("stack","heap","data")}
        initial_values = {sym["name"]: sym.get("value")
                          for sym in analysis if sym.get("location") in ("stack","heap","data") and sym.get("value") is not None}

        # 전역 프로브(문자열/스칼라)
        global_symbols = [sym for sym in analysis if sym.get("location") == "data"]
        gv_probe_lines = ['printf "__GV_BEGIN__\\n"']
        for sym in global_symbols:
            orig = sym["name"]; base = _base_name(orig)
            ty   = (sym.get("type") or "").strip().lower()
            if '[' in orig and ty == 'char':
                gv_probe_lines.append(f'printf "__GV__ {orig}=%s\\n", (char*) {base}')
            else:
                gv_probe_lines.append(f'printf "__GV__ {orig}="')
                gv_probe_lines.append(f'output {base}')
                gv_probe_lines.append('printf "\\n"')
        gv_probe_lines.append('printf "__GV_END__\\n"')

        # ---------- GDB 스크립트(printf/CRT skip, step 유지) ----------
        gdb_script = "\n".join([
            "set pagination off",
            "set print pretty off",
            # CRT/표준IO 안으로는 들어가지 않게
            "skip function printf",
            "skip function fprintf",
            "skip function vfprintf",
            "skip function vprintf",
            "skip function puts",
            "skip function putchar",
            "skip function _IO_printf",
            "skip function __stdio_common_vfprintf",
            "skip function __acrt_iob_func",
            "",
            "start",
            "while $pc",
            '  printf "##STEP##\\n"',
            "  frame",
            "  info line",
            "  info locals",
            *[f"  {ln}" for ln in gv_probe_lines],
            '  printf "__BT_BEGIN__\\n"',
            "  bt",
            '  printf "__BT_END__\\n"',
            "  step",   # next로 바꾸지 않음
            "end",
            "quit",
        ])
        gdb_path = os.path.abspath(os.path.join(UPLOAD_DIR, "debug.gdb"))
        with open(gdb_path, "w", encoding="utf-8") as f:
            f.write(gdb_script)
        gdb_output_path = os.path.abspath(os.path.join(UPLOAD_DIR, "gdb_output.txt"))
        with open(gdb_output_path, "w", encoding="utf-8") as fout:
            subprocess.run(
                f"gdb -q -batch -x \"{gdb_path}\" \"{exec_path}\"",
                cwd=UPLOAD_DIR, shell=True, stdout=fout, stderr=subprocess.STDOUT, text=True
            )
        with open(gdb_output_path, "r", encoding="utf-8", errors="replace") as f:
            output = f.read()

        # ---------- 힙 트래커(네가 쓰던 버전 유지) ----------
        heap_state = {}
        freed_ptrs = set()
        re_malloc  = re.compile(r'\b([A-Za-z_]\w*)\s*=\s*\([^;]*?\)\s*malloc\s*\(\s*(.+?)\s*\)')
        re_calloc  = re.compile(r'\b([A-Za-z_]\w*)\s*=\s*\([^;]*?\)\s*calloc\s*\(\s*(.+?)\s*,\s*(.+?)\s*\)')
        re_realloc = re.compile(r'\b([A-Za-z_]\w*)\s*=\s*\([^;]*?\)\s*realloc\s*\(\s*([A-Za-z_]\w*)\s*,\s*(.+?)\s*\)')
        re_free    = re.compile(r'\bfree\s*\(\s*([A-Za-z_]\w*)\s*\)')
        re_write   = re.compile(r'\b([A-Za-z_]\w*)\s*\[\s*(\d+)\s*\]\s*=\s*([^;]+)')
        re_strcpy  = re.compile(r'\bstrcpy\s*\(\s*([A-Za-z_]\w*)\s*,\s*"([^"]*)"\s*\)')

        def guess_count(expr: str):
            if not expr: return None
            m = re.search(r'(\d+)\s*\*\s*sizeof', expr)
            if m: return int(m.group(1))
            m = re.fullmatch(r'\s*(\d+)\s*', expr)
            if m: return int(m.group(1))
            return None

        def heap_alloc(var, count=None, kind="int[]"):
            d = heap_state.get(var, {})
            d["freed"] = False; d["string"] = None
            d["type"] = f"int[{count}]" if (kind=="int[]" and count is not None) else ("char[]" if kind=="char[]" else kind)
            if kind == "int[]":
                if count is not None:
                    d["values"] = d.get("values") or ["?"]*count
                    if len(d["values"]) != count:
                        d["values"] = (d["values"][:count] + ["?"]*count)[:count]
                else:
                    d["values"] = d.get("values") or None
            elif kind == "char[]":
                d["values"] = None
            heap_state[var] = d

        def heap_zero(var, count):
            d = heap_state.get(var, {})
            d["freed"] = False; d["type"] = f"int[{count}]"
            d["values"] = [0]*count; d["string"] = None
            heap_state[var] = d

        def heap_write_index(var, idx, expr_value):
            d = heap_state.get(var)
            if not d or d.get("freed"): return
            if d.get("type","").startswith("int["):
                try: val = int(str(expr_value).strip())
                except: val = str(expr_value).strip()
                if d.get("values") is None:
                    d["values"] = ["?"]*(idx+1)
                if idx >= len(d["values"]):
                    d["values"].extend(["?"]*(idx+1-len(d["values"]))); 
                d["values"][idx] = val; d["string"] = None
            elif d.get("type") == "char[]":
                d["string"] = None
            heap_state[var] = d

        def heap_set_string(var, s):
            d = heap_state.get(var, {})
            d["freed"] = False; d["type"] = "char[]"
            d["string"] = s; d["values"] = None
            heap_state[var] = d

        def heap_free(var):
            if var in heap_state: del heap_state[var]
            freed_ptrs.add(var)

        # ---------- 타임라인 ----------
        steps = output.split("##STEP##\n")
        global_data = [{
            "name": sym["name"], "type": sym["type"], "value": sym.get("value"),
            "pointer": sym.get("pointer", False), "points_to": sym.get("points_to"),
            "scope": sym.get("scope", "global")
        } for sym in global_symbols]

        timeline = []
        prev_stack, prev_heap = [], []
        prev_data = global_data.copy()
        step_counter = 0
        data_decls, seen_lines = [], set()
        last_func, last_line = None, None

        # 전역 선언 먼저 스냅샷
        for sym in global_symbols:
            ln = sym.get("line")
            if ln and ln not in seen_lines:
                seen_lines.add(ln)
                timeline.append({
                    "time": step_counter, "line_num": ln, "line": code_lines[ln-1],
                    "stack": {}, "heap": {},
                    "data": group_by_scope([{
                        "name": sym["name"], "type": sym["type"], "value": sym.get("value"),
                        "pointer": sym.get("pointer", False), "points_to": sym.get("points_to"),
                        "scope": "global"
                    }])
                })
                last_line = ln
                step_counter += 1

        for step in steps:
            lines = step.strip().splitlines()
            if not lines: continue

            info_line_no = None
            locals_raw = []   # info locals에서 수집(나중에 유저 프레임일 때만 사용)
            gv_reading = False
            bt_reading = False
            gv_values = {}
            bt_lines = []

            for raw in lines:
                s = raw.strip()
                if s.startswith("Line "):
                    m = re.match(r"Line (\d+) of", s)
                    if m: info_line_no = int(m.group(1)); continue

                if re.match(r"^\w+ = ", s) and not s.startswith("__GV__"):
                    try:
                        name, value = s.split(" = ", 1)
                        value = re.sub(r"^\(.*?\)\s*", "", value.strip())
                        value = clean_value_string(value)
                        var = {
                            "name": name.strip(), "type": "int", "value": value,
                            "pointer": isinstance(value, str) and value.startswith('&'),
                            "points_to": None, "scope": scope_map.get(name.strip(), "global")
                        }
                        if var["pointer"] and isinstance(var["value"], str) and len(var["value"]) > 1:
                            var["points_to"] = var["value"][1:]
                        locals_raw.append(var)
                    except:
                        pass
                    continue

                if s == "__GV_BEGIN__": gv_reading = True;  continue
                if s == "__GV_END__":   gv_reading = False; continue
                if gv_reading and s.startswith("__GV__ "):
                    try:
                        body = s[len("__GV__ "):]
                        nm, val = body.split("=", 1)
                        gv_values[nm.strip()] = clean_value_string(val.strip())
                    except:
                        pass
                    continue

                if s == "__BT_BEGIN__": bt_reading = True;  continue
                if s == "__BT_END__":   bt_reading = False; continue
                if bt_reading: bt_lines.append(s); continue

            # 현재 유저 프레임(#0) 기준으로 라인/함수 결정
            tuf = top_user_frame(bt_lines)
            if tuf:
                _, curr_func, curr_line = tuf
            else:
                curr_func, curr_line = None, info_line_no

            # ★None으로 흔들릴 때 직전 함수로 고정해서 같은 함수로 간주
            eff_func = curr_func or last_func

            if curr_line is None or not (1 <= curr_line <= len(code_lines)):
                continue

            line_text = code_lines[curr_line - 1]
            sanitized = re.sub(r'//.*$', '', line_text)
            is_printf_line = printf_re.search(sanitized) is not None

            # ---- 역행 필터(강화): 같은 함수(효과적으로)에서만 뒤로 가는 이동 차단 ----
            if last_line is not None and last_func is not None and curr_line is not None:
                if eff_func == last_func and curr_line < last_line:
                    prev_txt = code_lines[last_line - 1] if 1 <= last_line <= len(code_lines) else ""
                    if not (is_loopy(line_text) or is_loopy(prev_txt)):
                        continue

            # ---- 같은 줄 연속 중복 스킵(printf 줄은 예외) ----
            if timeline and timeline[-1].get("line_num") == curr_line and not is_printf_line:
                # 단, 다른 함수-같은 줄(매크로 등) 케이스는 드뭄 → 필요시 확장
                continue

            # 현재 프레임이 유저 소스인지(#0 프레임 검사)
            curr_is_user = False
            if bt_lines:
                m0 = bt_frame_full_re.match(bt_lines[0].strip())
                if m0 and os.path.basename(m0.group(3)) == source_basename:
                    curr_is_user = True

            # 허용 스코프 = 현재까지의 유저 프레임 함수 + main
            allowed_scopes = {fn for _, fn, _ in parse_user_frames(bt_lines)} | {"main"}

            # 로컬 변수: 현재 프레임이 유저 소스일 때만 반영(외부 프레임 로컬 차단)
            stack_vars = locals_raw if curr_is_user else []

            # 선언 전 로컬 차단 + 선언 줄 초기값 반영
            decl_inits_on_line = parse_decl_inits_for_line(line_text)
            filtered_stack_vars = []
            for v in stack_vars:
                nm = v["name"]; decl_line = declared_line_map.get(nm, None)
                if decl_line is not None and decl_line > 0:
                    if decl_line <= curr_line:
                        filtered_stack_vars.append(v)
                elif nm in decl_inits_on_line:
                    filtered_stack_vars.append(v)
            for v in filtered_stack_vars:
                nm = v["name"]; decl_line = declared_line_map.get(nm, None)
                v["scope"] = scope_map.get(nm, curr_func or "main")
                if decl_line == curr_line:
                    if nm in decl_inits_on_line:
                        v["value"] = decl_inits_on_line[nm]; v["pending_init"] = True
                    elif nm in initial_values:
                        v["value"] = str(initial_values[nm]); v["pending_init"] = True

            # 포인터 대입(p=&b;)
            pm = re_ptr_assign.search(sanitized)
            if pm:
                plhs, prhs = pm.group(1), pm.group(2)
                matched = False
                for v in filtered_stack_vars:
                    if v["name"] == plhs:
                        v["value"] = f"&{prhs}"; v["pointer"] = True; v["points_to"] = prhs
                        matched = True; break
                if not matched:
                    filtered_stack_vars.append({
                        "name": plhs, "type": "pointer", "value": f"&{prhs}",
                        "pointer": True, "points_to": prhs, "scope": curr_func or "main"
                    })

            # 힙 트래킹(줄 분석)
            m = re_malloc.search(sanitized)
            if m:
                var, expr = m.group(1), m.group(2); heap_alloc(var, guess_count(expr), "int[]")
            m = re_calloc.search(sanitized)
            if m:
                var, n_expr, _sz = m.group(1), m.group(2), m.group(3); heap_zero(var, guess_count(n_expr) or 1)
            m = re_realloc.search(sanitized)
            if m:
                lhs, inner, expr = m.group(1), m.group(2), m.group(3); heap_alloc(lhs, guess_count(expr), "int[]")
            for mm in re_write.finditer(sanitized):
                var, idx, rhs = mm.group(1), int(mm.group(2)), mm.group(3); heap_write_index(var, idx, rhs)
            m = re_strcpy.search(sanitized)
            if m: heap_set_string(m.group(1), m.group(2))
            m = re_free.search(sanitized)
            if m: heap_free(m.group(1))

            for v in filtered_stack_vars:
                if v["name"] in freed_ptrs:
                    v["value"] = "(freed)"

            # data (globals)
            data_vars = []
            for sym in analysis:
                if sym.get("location") == "data" and sym.get("line", 0) <= curr_line:
                    name = sym["name"]; base = _base_name(name)
                    val  = gv_values.get(name) or gv_values.get(base, sym.get("value"))
                    data_vars.append({
                        "name": name, "type": sym["type"], "value": val,
                        "pointer": sym.get("pointer", False), "points_to": sym.get("points_to"),
                        "scope": sym.get("scope", "global")
                    })

            # 힙 직렬화
            heap_vars_now = []
            for var, d in heap_state.items():
                if d.get("freed"): continue
                if d.get("string") is not None:
                    val = f"\"{d['string']}\""; typ = d.get("type", "char[]")
                elif d.get("values") is not None:
                    val = d["values"]; typ = d.get("type", "int[]")
                else:
                    val = "(heap)"; typ = d.get("type", "heap")
                heap_vars_now.append({
                    "name": var, "type": typ, "value": val,
                    "pointer": True, "points_to": None, "scope": "main"
                })

            # 병합 + 스코프 제한
            merged_stack = update_memory(prev_stack, filtered_stack_vars)
            pruned_stack = [v for v in merged_stack if v.get("scope", "global") in allowed_scopes]
            heap  = update_memory(prev_heap, heap_vars_now)
            data  = update_memory(prev_data, data_vars)

            # printf 캡처(+ *p 역참조)
            printed = None
            mprintf = printf_re.search(sanitized)
            if mprintf:
                fmt_raw = mprintf.group(1); args_raw = mprintf.group(2) or ""
                fmt = unescape_basic(fmt_raw)
                arg_tokens = split_args(args_raw)

                stack_obj_map = {v["name"]: v for v in pruned_stack}
                prev_stack_obj_map = {v["name"]: v for v in prev_stack}
                merged_obj = {**prev_stack_obj_map, **stack_obj_map}

                snap_locals = {k: v.get("value") for k, v in merged_obj.items()}
                snap_globals = {}
                for dv in data:
                    for _scope_name, items in group_by_scope([dv]).items():
                        for k, v in items.items():
                            snap_globals[k] = v.get("value")

                def resolve_arg(tok: str):
                    tok0 = re.sub(r'^\(.*?\)\s*', '', tok).strip()
                    md = re.match(r'^\*([A-Za-z_]\w*)$', tok0)
                    if md:
                        base = md.group(1)
                        pobj = merged_obj.get(base, {})
                        target = pobj.get("points_to")
                        if not target:
                            vv = pobj.get("value")
                            if isinstance(vv, str) and vv.startswith('&') and len(vv) > 1:
                                target = vv[1:]
                        if target:
                            if target in snap_locals and snap_locals[target] is not None:
                                return snap_locals[target]
                            if target in snap_globals and snap_globals[target] is not None:
                                return snap_globals[target]
                    if len(tok0) >= 2 and tok0[0] == '"' and tok0[-1] == '"':
                        return tok0
                    if tok0 in snap_locals and snap_locals[tok0] is not None:
                        return snap_locals[tok0]
                    if tok0 in snap_globals and snap_globals[tok0] is not None:
                        return snap_globals[tok0]
                    base = _base_name(tok0)
                    if base in snap_globals and snap_globals[base] is not None:
                        return snap_globals[base]
                    return tok0

                vals = [resolve_arg(t) for t in arg_tokens]
                vi = 0; out = []; i = 0
                while i < len(fmt):
                    ch = fmt[i]
                    if ch != '%':
                        out.append(ch); i += 1; continue
                    if i + 1 < len(fmt) and fmt[i+1] == '%':
                        out.append('%'); i += 2; continue
                    j = i + 1
                    while j < len(fmt) and fmt[j] not in 'diuocsxXsfFeEgGaA':
                        j += 1
                    if j >= len(fmt): break
                    spec = fmt[j]
                    arg = vals[vi] if vi < len(vals) else None
                    vi += 1
                    if spec in 'diu':
                        out.append(str(to_int(arg)))
                    elif spec == 's':
                        s = str(arg or '')
                        if len(s) >= 2 and s[0] == '"' and s[-1] == '"': s = s[1:-1]
                        out.append(s)
                    elif spec == 'c':
                        s = str(arg or '')
                        if len(s) >= 2 and s[0] == "'" and s[-1] == "'":
                            out.append(s[1:-1])
                        else:
                            out.append(chr(to_int(s)) if to_int(s) else '')
                    else:
                        out.append('%' + spec)
                    i = j + 1
                printed = ''.join(out)

            entry = {
                "time": step_counter,
                "line_num": curr_line,
                "line": line_text,
                "stack": group_by_scope(pruned_stack),
                "heap": group_by_scope(heap),
                "data": group_by_scope(data),
            }
            if printed is not None:
                entry["stdout"] = printed

            timeline.append(entry)
            prev_stack, prev_heap, prev_data = pruned_stack, heap, data
            last_func, last_line = eff_func, curr_line
            step_counter += 1

        return timeline

    except Exception as e:
        with open(os.path.join(UPLOAD_DIR, "gdb_output.txt"), "w", encoding="utf-8") as f:
            f.write(f"[simulate_with_gdb ERROR] {str(e)}\n")
        return []


#  컴파일 + 실행 + 분석 + 시뮬레이션
@app.post("/compile")
async def compile_and_analyze(code: str = Form(...), input: str = Form("")):
    if os.path.exists(UPLOAD_DIR):
        shutil.rmtree(UPLOAD_DIR)
    os.makedirs(UPLOAD_DIR)

    file_path = os.path.join(UPLOAD_DIR, FILENAME)
    exec_path = os.path.abspath(os.path.join(UPLOAD_DIR, EXEC_NAME))   # ★ a.out
    json_path = os.path.join(UPLOAD_DIR, "memory_analysis.json")

    # 1. 코드 저장
    with open(file_path, "w", encoding="utf-8", newline="") as f:
        f.write(code)

    # 2. 컴파일 (Linux/WSL: a.out)
    try:
        subprocess.run(["gcc", "-g", "-O0", FILENAME, "-o", EXEC_NAME],
                       cwd=UPLOAD_DIR,
                       check=True,
                       capture_output=True,
                       text=True)

    except subprocess.CalledProcessError as e:
        return JSONResponse(status_code=400, content={"error": e.stderr})

    # 3. 실행
    try:
        result = subprocess.run([exec_path],
                                cwd=UPLOAD_DIR,
                                check=True,
                                capture_output=True,
                                text=True)
        run_output = result.stdout
    except subprocess.CalledProcessError as e:
        return JSONResponse(status_code=400, content={"error": e.stderr})

    # 4. 정적 분석
    try:
        analysis = analyze_c_code(code, save_path=json_path)
    except Exception as e:
        analysis = {"error": str(e)}

    #5. 실행 시뮬레이션 (타임라인)
    # try:
    #     timeline = simulate_execution(code)
    #     timeline_path = os.path.join(UPLOAD_DIR, "timeline.json")
    #     with open(timeline_path, "w", encoding="utf-8") as f:
    #         json.dump(timeline, f, indent=2, ensure_ascii=False)
    # except Exception as e:
    #     timeline = {"error": str(e)}

    try:
        timeline = simulate_with_gdb(code, exec_path, file_path)
        timeline_path = os.path.join(UPLOAD_DIR, "steps.json")
        with open(timeline_path, "w", encoding="utf-8") as f:
            json.dump(timeline, f, indent=2, ensure_ascii=False)
    except Exception as e:
        timeline = {"error": str(e)}

    # 6. 결과 반환
    return {
        "output": run_output,
        "analysis": analysis,
        "timeline": timeline
    }


@app.get("/healthz")
async def health_check():
    """WSL 환경에서 서버 동작 확인용"""
    return {"status": "ok", "gcc": sh.which("gcc"), "gdb": sh.which("gdb")}

@app.get("/steps")
async def get_steps():
    file_path = os.path.join(UPLOAD_DIR, "steps.json")
    return FileResponse(file_path, media_type="application/json")

@app.get("/")
async def serve_index():
     return FileResponse(os.path.join(FRONTEND_BUILD_DIR, "index.html"))

@app.get("/{full_path:path}")
async def serve_react_routes(full_path: str):
    target = os.path.join(FRONTEND_BUILD_DIR, full_path)
    if os.path.exists(target) and os.path.isfile(target):
        return FileResponse(target)
    return FileResponse(os.path.join(FRONTEND_BUILD_DIR, "index.html"))