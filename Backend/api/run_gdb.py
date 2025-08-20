import subprocess
import os
import re

# C 소스를 파일로 저장
def save_code_to_file(code: str, filename="main.c"):
    with open(filename, "w", encoding="utf-8") as f:
        f.write(code)
    print(f"[+] C 코드가 %s에 저장되었습니다." % filename)

# GCC로 C 소스 컴파일
def compile_code(source_file="main.c", output_file="a.exe"):
    r = subprocess.run(
        ["gcc",
         "-O0", "-g3",
         "-fno-omit-frame-pointer",
         "-fno-inline",
         "-fno-optimize-sibling-calls",
         source_file, "-o", output_file],
        capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if r.returncode != 0:
        print("[!] 컴파일 실패:")
        print(r.stderr)
        return False
    print("[+] 컴파일 성공: %s" % output_file)
    return True

# 주석/공백 라인 여부 판정
def is_comment_or_blank(line: str, in_block_comment: bool):
    s = (line or "").strip()
    if s == "" or s in ("{", "}"):
        return True, in_block_comment
    if s.startswith("//"):
        return True, in_block_comment
    if "/*" in s:
        in_block_comment = True
    if "*/" in s:
        in_block_comment = False
        return True, in_block_comment
    if in_block_comment:
        return True, in_block_comment
    return False, in_block_comment

# 소스 파일을 1-인덱스로 로드
def load_source_lines(src="main.c"):
    with open(src, "r", encoding="utf-8", errors="ignore") as f:
        return [""] + [l.rstrip("\n") for l in f]

# 실행 가능한 소스 라인 목록 계산
def calc_executable_lines(src="main.c"):
    lines = load_source_lines(src)
    in_block = False
    exec_lines = []
    for i in range(1, len(lines)):
        skip, in_block = is_comment_or_blank(lines[i], in_block)
        if not skip:
            exec_lines.append(i)
    return exec_lines, lines

# 함수별 지역 변수 선언 라인 수집
def collect_decl_lines_by_func(src_path: str):
    lines = load_source_lines(src_path)
    func_map = {}
    func = None
    brace = 0

    func_pat = re.compile(
        r'^\s*'
        r'(?:[A-Za-z_]\w*(?:\s+|\s*\*+\s+)*)*'
        r'([A-Za-z_]\w*)\s*\([^;]*\)\s*\{'
    )

    decl_pat = re.compile(
        r'^\s*'
        r'(?:static\s+|const\s+|volatile\s+|register\s+)*'
        r'(?:(?:unsigned|signed)\s+)?'
        r'(?:(?:long\s+long|long|short)\s+)?'
        r'(?:int|char|float|double|bool)\s+'
        r'([^;]+);'
    )

    proto_pat = re.compile(r'\)\s*;')

    for i in range(1, len(lines)):
        line = lines[i]

        if func is None:
            m = func_pat.match(line)
            if m:
                func = m.group(1)
                func_map.setdefault(func, {})
                brace = 1
            continue

        brace += line.count("{")
        brace -= line.count("}")

        m = decl_pat.match(line)
        if m and not proto_pat.search(line):
            tail = m.group(1)
            for part in [p.strip() for p in tail.split(",") if p.strip()]:
                part = part.split("=", 1)[0]
                part = re.sub(r'\([^)]*\)', ' ', part)
                part = re.sub(r'\[[^\]]*\]', ' ', part).replace('*', ' ')
                tokens = [t for t in re.split(r'\s+', part.strip()) if t]
                if not tokens:
                    continue
                name = tokens[-1]
                if re.match(r'^[A-Za-z_]\w*$', name):
                    func_map[func][name] = i

        if brace <= 0:
            func = None

    return func_map

# 각 실행 라인에 BP를 걸고 스냅샷 출력하는 GDB 스크립트 생성
def generate_gdb_script_linebps(exec_lines, source_file="main.c"):
    script = [
        "set pagination off",
        "set confirm off",
        "set step-mode on",
        "set breakpoint pending on",
        "set backtrace limit 64",   # 중복 한 줄만 유지
        "directory .",

        # 시작 지점 1회 스냅샷
        "start",
        'printf "##STEP##\\n"',
        'printf "##BT##\\n"',
        "bt",
        "frame 0",
        "info line",
        'printf "##ARGS##\\n"',
        "info args",
        'printf "##LOCALS##\\n"',
        "info locals",
        'printf "##ENDSTEP##\\n"',
    ]

    for ln in exec_lines:
        script += [
            f"break {source_file}:{ln}",
            "commands",
            "  silent",
            '  printf "##STEP##\\n"',
            '  printf "##BT##\\n"',
            "  bt",
            "  frame 0",
            "  info line",
            '  printf "##ARGS##\\n"',
            "  info args",
            '  printf "##LOCALS##\\n"',
            "  info locals",
            '  printf "##ENDSTEP##\\n"',
            "  continue",
            "end",
        ]

    script += ["continue", "quit"]

    with open("gdb_script.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(script))

# GDB를 실행해 스냅샷 로그 수집
def run_gdb(binary="a.exe", exec_lines=None, source_file="main.c"):
    if exec_lines is None:
        exec_lines, _ = calc_executable_lines(source_file)
    generate_gdb_script_linebps(exec_lines, source_file)

    env = os.environ.copy()
    env["LC_ALL"] = "C"
    env["LANG"] = "C"

    r = subprocess.run(
        ["gdb", "--quiet", "--batch", "-x", "gdb_script.txt", binary],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env,
    )
    return r.stdout or ""

# 프로그램을 실행해 stdout을 줄 단위로 수집
def run_program_and_capture_stdout(binary="a.exe", timeout_sec=None):
    prog = os.path.abspath(binary) if not os.path.isabs(binary) else binary
    try:
        r = subprocess.run([prog], capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           timeout=timeout_sec)
        out = r.stdout or ""
    except subprocess.TimeoutExpired as e:
        out = e.stdout or ""
    return out.splitlines(keepends=True)

# GDB 출력 로그를 파싱하여 실행 프레임 순서를 구성
def parse_gdb_output_linebps(output, source_file="main.c"):
    # info line 백업 패턴 (환경 따라 다를 수 있음)
    RE_INFO_LINE = re.compile(r'Line\s+(\d+)\s+of\s+"?([^"]+)"?')

    # bt: 두 가지 형태 모두 잡기
    # A) "#1 main (...)"           → 함수명이 바로 나오는 형태
    RE_BT_FUNC_A = re.compile(r'^#(\d+)\s+([A-Za-z_][\w$.@]*)\s*\(')
    # B) "#1 0xADDR in main (...)" → 주소 뒤에 'in 함수명'이 나오는 형태
    RE_BT_FUNC_B = re.compile(r'^#(\d+)\s+0x[0-9a-fA-F]+\s+in\s+([A-Za-z_][\w$.@]*)\s*\(')

    # bt 위치: "#i ... at path:line"
    RE_BT_LOC    = re.compile(r'^#(\d+).*\s+at\s+(.+?):(\d+)\b')

    src = load_source_lines(source_file)
    src_base = os.path.basename(source_file)

    steps = []
    collecting = None          # None | "bt" | "args" | "locals"
    bt_names = {}              # {frame_index: func_name}
    cur_top_func = None
    cur_top_line = None
    cur_args = {}
    cur_locals = {}

    def flush_step():
        nonlocal bt_names, cur_top_func, cur_top_line, cur_args, cur_locals
        if not bt_names and cur_top_line is None and not cur_args and not cur_locals:
            bt_names = {}; cur_top_func = None; cur_top_line = None
            cur_args = {}; cur_locals = {}
            return
        # callstack: bottom -> top (큰 index → 아래, #0 → 맨 위)
        idxs = sorted(bt_names.keys())
        callstack = [{"func": bt_names[i], "index": i} for i in reversed(idxs)]
        steps.append({
            "func":   cur_top_func,
            "line":   cur_top_line,
            "args":   cur_args.copy(),
            "locals": cur_locals.copy(),
            "callstack": callstack,
        })
        bt_names = {}; cur_top_func = None; cur_top_line = None
        cur_args = {}; cur_locals = {}

    # 빈 출력 대비: 항상 tuple 반환
    if not isinstance(output, str) or not output:
        return [], [], []

    for raw in output.splitlines():
        line = raw.rstrip("\n")

        if line == "##STEP##":
            flush_step()
            collecting = None
            continue
        if line == "##BT##":
            collecting = "bt"
            continue
        if line == "##ENDSTEP##":
            flush_step()
            collecting = None
            continue

        if collecting == "bt":
            # 함수명 추출 (A/B 두 패턴 시도)
            mA = RE_BT_FUNC_A.match(line)
            mB = RE_BT_FUNC_B.match(line)
            if mA or mB:
                fi = int((mA or mB).group(1))
                fn = (mA or mB).group(2)
                bt_names[fi] = fn
                if fi == 0:
                    cur_top_func = fn

            # 파일:줄 추출 (특히 #0용)
            m2 = RE_BT_LOC.match(line)
            if m2:
                fi2 = int(m2.group(1)); path = m2.group(2); ln = int(m2.group(3))
                if fi2 == 0 and os.path.basename(path) == src_base:
                    cur_top_line = ln
            continue

        if line == "##ARGS##":
            collecting = "args"; continue
        if line == "##LOCALS##":
            collecting = "locals"; continue

        # 보조: info line에서도 잡히면 덮어쓰기
        if "Line " in line:
            mi = RE_INFO_LINE.search(line)
            if mi:
                ln = int(mi.group(1)); fn = os.path.basename(mi.group(2))
                if fn == src_base:
                    cur_top_line = ln
            continue

        if collecting in ("args", "locals") and "=" in line:
            k, v = line.split("=", 1)
            k = k.strip(); v = " ".join(v.strip().split())
            if re.match(r'^[A-Za-z_]\w*$', k):
                if collecting == "args":   cur_args[k]   = v
                else:                      cur_locals[k] = v
            continue

    flush_step()

    executed_lines = [s["line"] for s in steps]
    executed_code  = [src[ln] if ln else "" for ln in executed_lines]
    return executed_lines, executed_code, steps

PRINT_CALL_RE = re.compile(r'\b(printf|puts|putchar|fputs|fprintf)\s*\(')

# 한 소스 라인에서 출력 호출과 개행 여부를 추출
def split_print_calls(line_text: str):
    calls = []
    for m in PRINT_CALL_RE.finditer(line_text):
        func = m.group(1)
        tail = line_text[m.end():]
        arg = ""
        depth = 0
        for i,ch in enumerate(tail):
            if ch == '(':
                depth += 1
            elif ch == ')':
                if depth == 0:
                    arg = tail[:i]
                    break
                depth -= 1
        has_nl = False
        f = func
        a = arg

        if f == "puts":
            has_nl = True
        elif f in ("printf","fprintf"):
            if f == "fprintf" and "stdout" not in a:
                has_nl = False
            if "\\n" in a:
                has_nl = True
        elif f == "fputs":
            has_nl = False
        elif f == "putchar":
            if "'\\n'" in a or '"\\n"' in a:
                has_nl = True

        calls.append((f, has_nl))
    return calls

# C 코드를 컴파일/실행하고 타임라인을 콘솔로 출력
def trace_c_execution(code: str):
    save_code_to_file(code)
    if not compile_code():
        return

    exec_lines, _src = calc_executable_lines("main.c")
    decl_map = collect_decl_lines_by_func("main.c")

    gdb_output = run_gdb(exec_lines=exec_lines, source_file="main.c")
    executed_lines, executed_code, frames = parse_gdb_output_linebps(gdb_output, "main.c")

    stdout_queue = run_program_and_capture_stdout()

    timeline = []
    for idx, (ln, code_line, frame) in enumerate(zip(executed_lines, executed_code, frames)):
        f = frame.get("func", "main")
        locals_raw = dict(frame.get("locals") or {})
        filtered_locals = {}
        decls = decl_map.get(f, {})
        for name, val in locals_raw.items():
            dln = decls.get(name)
            if dln is None or ln > dln:
                filtered_locals[name] = val

        # trace_c_execution 내부 for 루프의 timeline.append 앞쪽을 이렇게 바꿔
        callstack = frame.get("callstack") or [{
            "index": 0,
            "func": frame.get("func", "main"),
            "line": frame.get("line"),
            "args": frame.get("args") or {},
            "locals": frame.get("locals") or {}
        }]

        stack_frames = []
        decls_map = collect_decl_lines_by_func("main.c")  # 이 파일에서는 정규식 판별을 그대로 사용 중

        for fr in callstack:
            fn = fr.get("func") or "?"
            ln_fr = fr.get("line")
            args_fr = fr.get("args") or {}
            locals_raw_fr = fr.get("locals") or {}

            filtered = {}
            decls = decls_map.get(fn, {})
            for name, val in locals_raw_fr.items():
                dln = decls.get(name)
                if dln is None or (ln_fr and ln_fr > dln):
                    filtered[name] = val

            stack_frames.append({
                "function": fn,
                "variables": {**args_fr, **filtered}
            })


        timeline.append({
            "time": idx,
            "line_index": ln,
            "line": code_line,
            "memory": {
                "stack": stack_frames,
                "heap": []
            },
            "output": ""
        })

    pending_owner_idx = None
    for i, snap in enumerate(timeline):
        calls = split_print_calls(snap["line"])
        for (_func, has_nl) in calls:
            if has_nl:
                token = stdout_queue.pop(0) if stdout_queue else ""
                owner = pending_owner_idx if pending_owner_idx is not None else i
                timeline[owner]["output"] += token
                pending_owner_idx = None
            else:
                pending_owner_idx = i

    print("[+] TIMELINE(JSON-like)]")
    for t in timeline:
        print(t)
