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
