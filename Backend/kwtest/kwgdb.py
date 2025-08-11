# gdb.py
import subprocess
import re

def save_code_to_file(code: str, filename="main.c"):
    with open(filename, "w", encoding="utf-8") as f:
        f.write(code)
    print(f"[+] C 코드가 {filename}에 저장되었습니다.")

def compile_code(source_file="main.c", output_file="a.exe"):
    result = subprocess.run(
        ["gcc", "-O0", "-g3", "-fno-omit-frame-pointer", source_file, "-o", output_file],
        capture_output=True,
        text=True,
        encoding="utf-8",   # 핵심
        errors="replace"    # 핵심
    )
    if result.returncode != 0:
        print("[!] 컴파일 실패:")
        print(result.stderr)
        return False
    print(f"[+] 컴파일 성공: {output_file}")
    return True


def generate_gdb_script(max_steps=200):
    script = """\
set pagination off
set confirm off
break main
run

"""
    for _ in range(max_steps):
        script += """\
printf "##STEP##\\n"
bt 1
info line
printf "##ARGS##\\n"
info args
printf "##LOCALS##\\n"
info locals
step
"""
    script += "quit\n"
    with open("gdb_script.txt", "w", encoding="utf-8") as f:
        f.write(script)

import os

def run_program_and_capture_stdout(binary="a.exe"):
    # Windows에서는 './a.exe' 대신 그냥 'a.exe' 또는 절대경로 사용
    prog = os.path.abspath(binary) if not os.path.isabs(binary) else binary
    r = subprocess.run(
        [prog],
        capture_output=True,
        text=True,
        encoding="utf-8",   # 핵심
        errors="replace"    # 깨지는 문자는 대체
    )
    # r.stdout이 None이어도 안전하게 처리
    out = r.stdout or ""
    return out.splitlines(keepends=True)

def run_gdb(binary="a.exe", max_steps=200):
    generate_gdb_script(max_steps)
    result = subprocess.run(
        ["gdb", "--batch", "-x", "gdb_script.txt", binary],
        capture_output=True,
        text=True,          # text=True 명시
        encoding="utf-8",   # 핵심
        errors="replace"    # 핵심: ignore보다 디버깅에 유리
    )
    return result.stdout or ""


def is_comment_line(line: str, in_block_comment: bool):
    stripped = line.strip()
    # 한 줄 주석
    if stripped.startswith("//"):
        return True, in_block_comment
    # 블록 주석 시작
    if "/*" in stripped:
        in_block_comment = True
    # 블록 주석 종료
    if "*/" in stripped:
        in_block_comment = False
        return True, in_block_comment
    if in_block_comment:
        return True, in_block_comment
    return False, in_block_comment

def extract_function_decls(source_lines):
    """
    함수 선언 줄 추출 (예: int main() {, void foo(int param) { )
    딕셔너리로 func명 -> 선언 줄 번호 매핑 반환
    """
    func_decl_pattern = re.compile(r'^\s*([a-zA-Z_][a-zA-Z0-9_\s\*]+)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\([^;]*\)\s*\{')
    func_decl_lines = dict()
    for i, line in enumerate(source_lines, start=1):
        m = func_decl_pattern.match(line)
        if m:
            func_name = m.group(2).strip()
            func_decl_lines[func_name] = i
    return func_decl_lines

def parse_gdb_output(output, source_file="main.c"):
    frame_pattern = re.compile(r'#\d+\s+(\S+).* at (\S+):(\d+)')
    executed_lines = []
    executed_code = []
    call_stack = []  # 함수 호출 스택: (func_name, last_executed_line)
    prev_func = None
    prev_line = None
    in_block_comment = False

    try:
        with open(source_file, "r", encoding="utf-8") as f:
            source_lines = f.readlines()
    except UnicodeDecodeError:
        with open(source_file, "r", encoding="utf-8", errors="ignore") as f:
            source_lines = f.readlines()

    func_decl_lines = extract_function_decls(source_lines)

    lines = output.splitlines()
    for line in lines:
        m = frame_pattern.search(line)
        if m:
            func, file, line_no = m.groups()
            line_no = int(line_no)

            # 함수 호출 감지: 이전 함수와 다르고 이전 함수가 있고, 호출된 함수의 선언 줄이 현재 줄이 아니면 호출 시작으로 판단
            if prev_func != func:
                # 이전 함수가 있었으면 복귀한 줄 저장 (call_stack에서 제거)
                if call_stack and call_stack[-1][0] == prev_func:
                    # 복귀 후 이전 함수 다음 줄로 간다고 가정하여 마지막 실행 줄 갱신
                    call_stack.pop()

                # 새 함수 호출 시 함수 선언 줄 삽입
                if func in func_decl_lines:
                    decl_line_no = func_decl_lines[func]
                    if decl_line_no not in executed_lines:
                        decl_code_line = source_lines[decl_line_no - 1].rstrip()
                        is_comment, in_block_comment = is_comment_line(decl_code_line, False)
                        if not is_comment and decl_code_line != "":
                            executed_lines.append(decl_line_no)
                            executed_code.append(decl_code_line)

                # 호출 스택에 새 함수 추가
                call_stack.append((func, line_no))

            # 현재 줄 실행 (주석 아니고 유효하면 추가)
            if 1 <= line_no <= len(source_lines):
                code_line = source_lines[line_no - 1].rstrip()
                is_comment, in_block_comment = is_comment_line(code_line, in_block_comment)
                if not is_comment and code_line != "":
                    # 중복 연속 줄 제거
                    if len(executed_lines) == 0 or line_no != executed_lines[-1]:
                        executed_lines.append(line_no)
                        executed_code.append(code_line)

            prev_func = func
            prev_line = line_no

    return executed_lines, executed_code

def parse_gdb_output_enhanced(output, source_file="main.c"):
    # 기존 정규식 재활용
    frame_pattern = re.compile(r'#\d+\s+(\S+).* at (\S+):(\d+)')
    executed_lines, executed_code, frames = [], [], []

    with open(source_file, "r", encoding="utf-8", errors="ignore") as f:
        source_lines = f.readlines()
    func_decl_lines = extract_function_decls(source_lines)

    lines = output.splitlines()
    in_block_comment = False

    cur_func = None
    cur_line_no = None
    collecting = None  # None | "args" | "locals"
    cur_args = {}
    cur_locals = {}

    def flush_step():
        if cur_line_no is None:
            return
        code_line = source_lines[cur_line_no - 1].rstrip() if 1 <= cur_line_no <= len(source_lines) else ""
        is_comment, _tmp = is_comment_line(code_line, False)
        if not is_comment and code_line != "":
            if not executed_lines or executed_lines[-1] != cur_line_no:
                executed_lines.append(cur_line_no)
                executed_code.append(code_line)
                frames.append({
                    "func": cur_func or "",
                    "line": cur_line_no,
                    "args": cur_args.copy(),
                    "locals": cur_locals.copy()
                })

    IDENT_RE = re.compile(r'^[A-Za-z_]\w*$')

    def parse_var_line(s: str):
        s = s.strip()
        if "=" not in s:
            return None, None
        k, v = s.split("=", 1)
        k = k.strip()
        v = " ".join(v.strip().split())  # 공백 정규화
        if not IDENT_RE.match(k):        # 정상 식별자만 허용
            return None, None
        return k, v

    for raw in lines:
        line = raw.rstrip("\n")

        if line == "##STEP##":
            # 이전 step flush
            flush_step()
            # 다음 step 준비
            cur_args.clear()
            cur_locals.clear()
            collecting = None
            cur_func = None
            cur_line_no = None
            continue

        if line == "##ARGS##":
            collecting = "args";  continue
        if line == "##LOCALS##":
            collecting = "locals";  continue

        m = frame_pattern.search(line)
        if m:
            cur_func, file, ln = m.groups()
            cur_line_no = int(ln)
            # 함수 선언 라인 삽입(원하면): 여기서는 스텝 단위 스냅샷만 만들 거라 생략해도 됨
            continue

        if collecting == "args":
            k, v = parse_var_line(line)
            if k: cur_args[k] = v
            continue
        if collecting == "locals":
            k, v = parse_var_line(line)
            if k: cur_locals[k] = v
            continue

        # info line 백업: "Line 27 of "main.c" ..."
        if cur_line_no is None:
            mi = re.search(r'Line\s+(\d+)\s+of\s+"?([^"]+)"?', line)
            if mi:
                cur_line_no = int(mi.group(1))

    # 마지막 step flush
    flush_step()
    return executed_lines, executed_code, frames


def trace_c_execution(code: str):
    save_code_to_file(code)

    if not compile_code():
        return

    # 1) gdb로 스텝 기반 실행 정보 수집
    gdb_output = run_gdb()
    executed_lines, executed_code, frames = parse_gdb_output_enhanced(gdb_output)  
    # ↑ 아래 3번에서 추가 설명. frames는 각 step의 {func, line, args, locals}

    # 2) 일반 실행으로 printf 출력 수집
    stdout_queue = run_program_and_capture_stdout()

    # 3) 타임라인 조립
    timeline = []
    cumulative_output = ""   # 출력 누적 (콘솔 출력처럼)
    for idx, (ln, code_line, frame) in enumerate(zip(executed_lines, executed_code, frames)):
        step_output = ""
        if "printf(" in code_line:
            # printf가 실행된 스텝이면 다음 출력 토큰 소비
            if stdout_queue:
                token = stdout_queue.pop(0)
                step_output = token
                cumulative_output += token

        snapshot = {
            "time": idx,
            "line_index": ln,
            "line": code_line,
            "memory": {
                # 간단 MVP: 현재 프레임(스택 top)만 먼저 넣고, 원하면 콜스택 전체로 확장
                "stack": [{
                    "function": frame["func"],
                    "args": frame.get("args", {}),
                    "locals": frame.get("locals", {})
                }],
                "heap": []  # (선택) 나중에 malloc/free 추적 추가
            },
            "output": step_output  # 스텝에서 새로 생긴 출력만
            # 필요하면 "stdout": cumulative_output 로 누적본도 같이 제공
        }
        timeline.append(snapshot)

    # 출력
    print("[+] TIMELINE(JSON-like)]")
    for t in timeline:
        print(t)

if __name__ == "__main__":
    c_code = r"""
#include <stdio.h>

// 함수 선언 (함수 원형)
int add(int a, int b);

int main() {
  int num1 = 10, num2 = 5;
  int sum;

  // 함수 호출
  sum = add(num1, num2);

  printf("두 수의 합: %d\n", sum);

  return 0;
}

// 함수 정의
int add(int a, int b) {
  return a + b;
}
"""
    trace_c_execution(c_code)
