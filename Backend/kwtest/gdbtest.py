import subprocess
import os
import re

# =========================
#  1) 저장 & 컴파일
# =========================

def save_code_to_file(code: str, filename="main.c"):
    with open(filename, "w", encoding="utf-8") as f:
        f.write(code)
    print(f"[+] C 코드가 {filename}에 저장되었습니다.")

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
    print(f"[+] 컴파일 성공: {output_file}")
    return True


# =========================
#  2) 소스 라인 스캔
# =========================

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

def load_source_lines(src="main.c"):
    with open(src, "r", encoding="utf-8", errors="ignore") as f:
        return [""] + [l.rstrip("\n") for l in f]  # 1-index

def calc_executable_lines(src="main.c"):
    lines = load_source_lines(src)
    in_block = False
    exec_lines = []
    for i in range(1, len(lines)):
        skip, in_block = is_comment_or_blank(lines[i], in_block)
        if not skip:
            exec_lines.append(i)
    return exec_lines, lines

# (선언 라인 맵: { func: {var: decl_line} })
def collect_decl_lines_by_func(src_path: str):
    lines = load_source_lines(src_path)
    func_map = {}
    func = None
    brace = 0
    func_pat = re.compile(r'^\s*[A-Za-z_][\w\s\*\(\)]+\s+([A-Za-z_]\w*)\s*\([^;]*\)\s*\{')
    decl_pat = re.compile(
        r'^\s*(?:static\s+)?(?:const\s+)?'
        r'(?:(?:unsigned|signed)\s+)?'
        r'(?:(?:long\s+long|long|short)\s+)?'
        r'(?:int|char|float|double)\s+([^;]+);'
    )
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
        if m:
            tail = m.group(1)
            for part in [p.strip() for p in tail.split(",")]:
                part = part.split("=", 1)[0].strip()
                part = part.replace("*", " ")
                part = re.sub(r'\[[^\]]*\]', ' ', part)
                tokens = [t for t in re.split(r'\s+', part) if t]
                if tokens:
                    name = tokens[-1]
                    if re.match(r'^[A-Za-z_]\w*$', name):
                        func_map[func][name] = i
        if brace <= 0:
            func = None
    return func_map


# =========================
#  3) GDB 스크립트(라인별 BP + 시작 스냅샷)
# =========================

def generate_gdb_script_linebps(exec_lines, source_file="main.c"):
    """
    - start 직후 현재 위치를 1회 로그(첫 printf 줄에서 출력이 소비되도록)
    - main.c의 모든 실행 라인에 break + 공통 commands(로그 후 continue)
    - 마지막에 단 한 번 continue로 끝까지 실행
    """
    script = ["set pagination off",
              "set confirm off",
              "set step-mode on",
              "set breakpoint pending on",
              "directory .",
              # 출력 함수 내부 진입 방지(안전빵)
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
              # ▶ 시작 스냅샷 (여기서 'continue' 금지!)
              'printf "##STEP##\\n"',
              "frame 0",
              "info line",
              'printf "##ARGS##\\n"',
              "info args",
              'printf "##LOCALS##\\n"',
              "info locals",
              ]

    # 🔧 여기서 모든 라인에 브레이크포인트 설치 + commands 지정
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
            "continue",
            "end"
        ]

    # ✅ 이제서야 한 번만 continue 해서 끝까지 실행
    script.append("continue")
    script.append("quit")

    with open("gdb_script.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(script))

def run_gdb(binary="a.exe", exec_lines=None, source_file="main.c"):
    if exec_lines is None:
        exec_lines, _ = calc_executable_lines(source_file)
    generate_gdb_script_linebps(exec_lines, source_file)
    r = subprocess.run(
        ["gdb", "--batch", "-x", "gdb_script.txt", binary],
        capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return r.stdout or ""


# =========================
#  4) 일반 실행(stdout 수집)
# =========================

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


# =========================
#  5) GDB 로그 파싱
# =========================

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
        # (줄+함수) 중복 억제
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


# =========================
#  6) 타임라인 조립 (+ 출력 매칭 & 로컬 필터)
# =========================

PRINT_RE = re.compile(r'\b(printf|puts|putchar|fputs|fprintf)\b')

def trace_c_execution(code: str):
    save_code_to_file(code)
    if not compile_code():
        return

    # 실행 가능한 라인 목록
    exec_lines, _src = calc_executable_lines("main.c")
    decl_map = collect_decl_lines_by_func("main.c")

    # (A) GDB: 모든 라인에서 스냅샷 수집
    gdb_output = run_gdb(exec_lines=exec_lines, source_file="main.c")
    executed_lines, executed_code, frames = parse_gdb_output_linebps(gdb_output, "main.c")

    # (B) 일반 실행: stdout 토큰 수집
    stdout_queue = run_program_and_capture_stdout()

    # (C) 타임라인 + 출력 매칭 & 로컬 변수 필터링
    timeline = []
    for idx, (ln, code_line, frame) in enumerate(zip(executed_lines, executed_code, frames)):
        # 출력 매칭: 한 줄 내 호출 개수만큼 소비
        emit_cnt = len(PRINT_RE.findall(code_line))
        step_output = ""
        for _ in range(emit_cnt):
            if stdout_queue:
                step_output += stdout_queue.pop(0)

        # 로컬 변수: 선언 라인 이후만 노출
        f = frame.get("func", "main")
        locals_raw = dict(frame.get("locals") or {})
        filtered_locals = {}
        decls = decl_map.get(f, {})
        for name, val in locals_raw.items():
            dln = decls.get(name)
            if dln is None or ln >= dln:
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
            "output": step_output
        })

    print("[+] TIMELINE(JSON-like)]")
    for t in timeline:
        print(t)


# =========================
#  7) 데모 입력 (네가 준 코드 그대로 써도 됨)
# =========================

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
