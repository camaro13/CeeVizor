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

import re

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
    script = ["set pagination off",
              "set confirm off",
              "set step-mode on",
              "set breakpoint pending on",
              "directory .",
              "skip function printf",
              "skip function fprintf",
              "skip function vprintf",
              "skip function puts",
              "skip function fputs",
              "skip function putchar",
              "skip function __mingw_printf",
              "skip function __mingw_fprintf",
              "skip function __mingw_vprintf",
              "skip function __msvcrt_printf",
              "skip function __msvcrt_fprintf",
              "start",
              'printf "##STEP##\\n"',
              "frame 0",
              "info line",
              'printf "##ARGS##\\n"',
              "info args",
              'printf "##LOCALS##\\n"',
              "info locals",
              'printf "##ENDCOLLECT##\\n"',
              ]

    for ln in exec_lines:
        script.append(f"break {source_file}:{ln}")
        script += [
            "commands",
            "silent",
            'printf "##STEP##\\n"',
            "frame 0",
            "info line",
            'printf "##ARGS##\\n"',
            "info args",
            'printf "##LOCALS##\\n"',
            "info locals",
            'printf "##ENDCOLLECT##\\n"',
            "continue",
            "end"
        ]

    script.append("continue")
    script.append("quit")

    with open("gdb_script.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(script))

# GDB를 실행해 스냅샷 로그 수집
def run_gdb(binary="a.exe", exec_lines=None, source_file="main.c"):
    if exec_lines is None:
        exec_lines, _ = calc_executable_lines(source_file)
    generate_gdb_script_linebps(exec_lines, source_file)
    r = subprocess.run(
        ["gdb", "--batch", "-x", "gdb_script.txt", binary],
        capture_output=True, text=True, encoding="utf-8", errors="replace"
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
    RE_INFO_LINE = re.compile(r'Line\s+(\d+)\s+of\s+"?([^"]+)"?')
    RE_FUNC      = re.compile(r'^#0\s+([A-Za-z_][\w$.@]*)\s*\(')

    src = load_source_lines(source_file)
    N = len(src) - 1
    src_base = os.path.basename(source_file)

    def code(ln): return src[ln] if 1 <= ln <= N else ""

    executed_lines, executed_code, frames = [], [], []
    in_block_comment = False

    cur_func = "main"
    cur_line = None
    collecting = None
    args = {}
    locals_ = {}

    def flush():
        nonlocal args, locals_, cur_func, cur_line, in_block_comment
        if cur_line is None:
            return
        s = code(cur_line)
        skip, in_block_comment = is_comment_or_blank(s, in_block_comment)
        if skip:
            args.clear(); locals_.clear(); cur_line = None
            return
        if executed_lines and executed_lines[-1] == cur_line and frames and frames[-1]["func"] == cur_func:
            args.clear(); locals_.clear(); cur_line = None
            return
        executed_lines.append(cur_line)
        executed_code.append(s)
        frames.append({
            "func": cur_func,
            "line": cur_line,
            "args": args.copy(),
            "locals": locals_.copy()
        })
        args.clear(); locals_.clear(); cur_line = None

    for raw in output.splitlines():
        line = raw.rstrip("\n")

        if line == "##STEP##":
            flush()
            cur_func = "main"; cur_line = None
            collecting = None
            continue

        if line.startswith("#0 "):
            m = RE_FUNC.match(line)
            if m:
                cur_func = m.group(1)
            continue

        if line == "##ARGS##":
            collecting = "args"; continue
        if line == "##LOCALS##":
            collecting = "locals"; continue
        if line == "##ENDCOLLECT##": 
            collecting = None
            continue

        if "Line " in line:
            mi = RE_INFO_LINE.search(line)
            if mi:
                ln = int(mi.group(1)); fn = os.path.basename(mi.group(2))
                if fn == src_base:
                    cur_line = ln
            continue

        if collecting in ("args", "locals"):
            if "=" in line:
                k, v = line.split("=", 1)
                k = k.strip(); v = " ".join(v.strip().split())
                if re.match(r'^[A-Za-z_]\w*$', k):
                    if collecting == "args":   args[k]   = v
                    else:                      locals_[k] = v
            continue

    flush()
    return executed_lines, executed_code, frames

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

        timeline.append({
            "time": idx,
            "line_index": ln,
            "line": code_line,
            "memory": {
                "stack": [{
                    "function": f,
                    "variables": {**(frame.get("args") or {}), **filtered_locals}
                }],
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

if __name__ == "__main__":
    c_code = r"""
#include <stdio.h>
#include <stdlib.h>

int global_var = 10;        // 데이터 영역 (초기화된 전역변수)
static int static_var = 20; // 데이터 영역 (static 변수)

void foo(int param) {
    int stack_var = 30;    

    int* heap_var = (int*)malloc(sizeof(int));
    if (heap_var == NULL) return;
    *heap_var = 40;

    printf("global_var: %d\n", global_var);
    printf("static_var: %d\n", static_var);
    printf("param: %d\n", param);
    printf("stack_var: %d\n", stack_var);
    printf("*heap_var: %d\n", *heap_var);

    free(heap_var); 
}

int main() {
    foo(50);
    return 0;
}

"""
    trace_c_execution(c_code)
