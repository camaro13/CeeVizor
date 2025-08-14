// main.c
#include <stdio.h>
#include <stdlib.h>

int G_init = 10;
static int SG_init = 32;
int G_bss;
static int SG_bss;

static void swap(int *a, int *b) {
    int tmp = *a;
    *a = *b;
    *b = tmp;
    printf("swap: a=%d b=%d\n", *a, *b);
}

static int sum_heap(int n) {
    int *p = (int*)malloc(sizeof(int));
    if (!p) return -1;
    *p = n;
    int acc = 0;
    for (int i = 0; i < 3; ++i) {
        acc += *p + i;
    }
    printf("sum_heap: *p=%d acc=%d\n", *p, acc);
    free(p);
    return acc;
}

static int bump_static(int x) {
    static int cnt;
    cnt += x;
    printf("bump_static: cnt=%d\n", cnt);
    return cnt;
}

static int twice_malloc(int n) {
    int *p = (int*)malloc(sizeof(int));
    int *q = (int*)malloc(sizeof(int));
    if (!p || !q) return -1;
    *p = n;
    *q = n + 1;
    int r = *p + *q;
    printf("twice_malloc: p=%d q=%d r=%d\n", *p, *q, r);
    free(p);
    free(q);
    return r;
}

int main(void) {
    int a = 7, b = 3;
    printf("globals: G_init=%d G_bss=%d SG_init=%d SG_bss=%d\n", G_init, G_bss, SG_init, SG_bss);

    swap(&a, &b);

    int s = sum_heap(a + b);
    int t1 = bump_static(1);
    int t2 = bump_static(2);
    int t3 = twice_malloc(s);

    printf("main: a=%d b=%d s=%d t1=%d t2=%d t3=%d\n", a, b, s, t1, t2, t3);
    return 0;
}
