#include <stdio.h>
int as (int a, int b)
{
    int num = 190;
    a += num;
    return a + b;
}

int main()
{
    int a = 193;
    int b = 184;
    printf("%d", as(a, b));
}