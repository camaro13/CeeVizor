#include <stdio.h>

// 함수 선언 (함수 원형)
int add(int a, int b);

int main() {
  int num1 = 11, num2 = 5;
  int sum;

  // 함수 호출
  sum = add(num1, num2);

  printf("두 수의 합: %d\n", sum);

  return 0;
}

// 함수 정의
int add(int a, int b) {
  return a + b;
}