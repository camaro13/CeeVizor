#include <stdio.h>

void add(float* result, float a, float b) {
    *result = a + b;
}

void subtract(float* result, float a, float b) {
    *result = a - b;
}

void multiply(float* result, float a, float b) {
    *result = a * b;
}

void divide(float* result, float a, float b) {
    if (b != 0)
        *result = a / b;
    else {
        printf("0À¸·Î ³ª´­ ¼ö ¾ø½À´Ï´Ù.\n");
        *result = 0;
    }
}

int main() {
    float a = 12.0, b = 4.0;
    float result;

    add(&result, a, b);
    printf("µ¡¼À °á°ú: %.2f\n", result);

    subtract(&result, a, b);
    printf("»¬¼À °á°ú: %.2f\n", result);

    multiply(&result, a, b);
    printf("°ö¼À °á°ú: %.2f\n", result);

    divide(&result, a, b);
    printf("³ª´°¼À °á°ú: %.2f\n", result);

    return 0;
}
