
#include <stdio.h>
#include <stdlib.h>

int g = 10;
static int s = 20;

int add(int a, int b) {
    int sum = a + b;
    printf("add=%d\n", sum);
    return sum;
}

int main(void) {
    setvbuf(stdout, NULL, _IONBF, 0);
    int x = 3, y = 4;
    int *p = (int*)malloc(sizeof(int));
    *p = add(x, y);
    printf("p=%d\n", *p);
    free(p);
    return 0;
}
