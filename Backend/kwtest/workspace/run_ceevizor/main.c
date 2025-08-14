// file: main.c
#include <stdio.h>
#include <stdlib.h>

int G_init = 10;
static int SG_init = 32;
int G_bss;
static int SG_bss;

static void swap(int *a, int *b) {
    int tmp = *a;                // 선언+초기화 (일부 gdb에서 info locals 빈값)
    *a = *b;
    *b = tmp;
    printf("swap: a=%d b=%d\n", *a, *b);
}

static int sum_heap(int n) {
    int *p = (int*)malloc(sizeof(int));
    if (!p) return -1;
    *p = n;

    int acc = 0;
    for (int i = 0; i < 3; ++i) {   // i 선언 라인도 종종 locals 빈값
        acc += *p + i;
    }
    printf("sum_heap: *p=%d acc=%d\n", *p, acc);
    free(p);
    return acc;
}

int main(void) {
    int a = 7, b = 3;   // ← 여기서는 a,b가 잘 보임(대부분 환경)
    printf("globals: G_init=%d G_bss=%d SG_init=%d SG_bss=%d\n", G_init, G_bss, SG_init, SG_bss);

    swap(&a, &b);       // ← 이 호출 라인이나 바로 이전/다음 printf 라인에서
                        //    gdb가 main의 info locals를 빈값으로 주는 경우가 있음

    int s = sum_heap(a + b);  // ← 여기도 마찬가지로 빈값이 들어오기 쉽다
    printf("main: a=%d b=%d s=%d\n", a, b, s);

    return 0;
}
