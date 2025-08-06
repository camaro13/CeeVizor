# gdb.py
# 줄번호와 코드 나오게 했고, 코드 수정해서 print말고 다른 코드에 코드파싱과 합칠수있게 다시 만들어야 함
# 그리고 로그 남기는것도 파일하나 만들어서 거기다가 넣을수 있게끔
import subprocess
import re

def save_code_to_file(code: str, filename="main.c"):
    with open(filename, "w", encoding="utf-8") as f:
        f.write(code)
    print(f"[+] C 코드가 {filename}에 저장되었습니다.")

def compile_code(source_file="main.c", output_file="a.out"):
    result = subprocess.run(["gcc", "-g", source_file, "-o", output_file],
                            capture_output=True, text=True)
    if result.returncode != 0:
        print("[!] 컴파일 실패:")
        print(result.stderr)
        return False
    print(f"[+] 컴파일 성공: {output_file}")
    return True

def generate_gdb_script(max_steps=200):
    script = """
set pagination off
start
"""
    for _ in range(max_steps):
        script += """
printf "##STEP##\\n"
frame
info line
step
"""
    script += "quit\n"
    with open("gdb_script.txt", "w", encoding="utf-8") as f:
        f.write(script)

def run_gdb(binary="a.out", max_steps=200):
    generate_gdb_script(max_steps)
    result = subprocess.run(
        ["gdb", "--batch", "-x", "gdb_script.txt", binary],
        capture_output=True,
        encoding="utf-8",
        errors="ignore"
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

def trace_c_execution(code: str):
    save_code_to_file(code)
    if not compile_code():
        return

    gdb_output = run_gdb()

    executed_lines, executed_code = parse_gdb_output(gdb_output)

    print("[+] 실제 실행 순서대로 실행된 줄 번호:")
    print(executed_lines)
    print("\n[+] 실행된 코드 라인:")
    for ln, code_line in zip(executed_lines, executed_code):
        print(f"{ln}: {code_line}")

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
