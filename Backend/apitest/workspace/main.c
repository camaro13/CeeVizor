#include <stdio.h>

int counter = 0;        
char msg[20] = "Hello"; 

void increment_counter() {
    counter++;
}

int multiply(int x, int y) {
    int product = x * y;
    return product;
}

int main() {
    int a = 4;
    int b = 5;
    int result = multiply(a, b);

    increment_counter();

    char *p = msg; 
    printf("%s world! Result=%d, Counter=%d\n", p, result, counter);

    return 0;
}
