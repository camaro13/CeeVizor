# demo_kwgdb_test.py
from textwrap import dedent
from kwgdb import trace_c_execution

CASE_BASIC = dedent(r"""
#include <stdio.h>
int main(void){
    int a = 2;
    printf("A: %d\n", a);
    printf("B");
    printf("C\n");
    return 0;
}
""")

CASE_FUNC = dedent(r"""
#include <stdio.h>
void bar(int x){ printf("bar:%d\n", x+1); }
void foo(int x){ printf("foo:%d\n", x); bar(x); }
int main(void){
    printf("start\n");
    foo(42);
    printf("end\n");
    return 0;
}
""")

CASE_STDERR = dedent(r"""
#include <stdio.h>
int main(void){
    fprintf(stderr, "E");
    printf("O\n");
    return 0;
}
""")

def run(label, code, **kw):
    print("="*80)
    print(f"[ RUN ] {label}")
    print("="*80)
    trace_c_execution(code, return_result=False, **kw)
    print()

if __name__ == "__main__":
    run("basic_stdout_tail_merge", CASE_BASIC, max_steps=50, merge_tail=True, step_into_user=False)
    run("func_no_step_into_user", CASE_FUNC, max_steps=80, merge_tail=True, step_into_user=False)
    run("func_step_into_user",   CASE_FUNC, max_steps=120, merge_tail=True, step_into_user=True)
    run("stderr_stdout_mix", CASE_STDERR, max_steps=30, merge_tail=True, step_into_user=False)
