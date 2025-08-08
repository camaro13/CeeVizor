
#include <stdio.h>

int add(int a, int b);

int main() {
    int x = 3, y = 4;
    int result = add(x, y);
    printf("Result: %d\n", result);
    return 0;
}

int add(int a, int b) {
    return a + b;
}
