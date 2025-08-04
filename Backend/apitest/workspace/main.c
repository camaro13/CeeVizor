#include <stdio.h>
int c = 0;
void aii() {
    int b = 9;
    printf("%d", b);
}
int main() {
    int a = 8;
    int *p = &a;
    aii();
    return 0;
}
