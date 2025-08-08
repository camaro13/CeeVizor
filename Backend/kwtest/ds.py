# test_gdb.py
from kwgdb import trace_c_execution  # gdb.py 모듈에서 함수 임포트

def main():
    c_code = """
#include <stdio.h>

int add(int a, int b);

int main() {
    int x = 3, y = 4;
    int result = add(x, y);
    printf("Result: %d\\n", result);
    return 0;
}

int add(int a, int b) {
    return a + b;
}
"""

    steps = trace_c_execution(c_code, return_result=True, max_steps=100)

    print(f"[Test] 총 단계 수: {len(steps)}")
    for i, step in enumerate(steps, start=1):
        print(f"Step {i}: func={step['func']}, line={step['line_no']}")
        print(f"  코드: {step['code_line']}")
        if step['vars']:
            print(f"  변수: {step['vars']}")
        if step['raw_output']:
            print(f"  출력: {step['raw_output']}")
        print("-" * 40)

if __name__ == "__main__":
    main()
