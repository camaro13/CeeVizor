#include <stdio.h>

int main() {
    int s = 42;
    int *q = &s;
    *q = 539;
    return 0;
}