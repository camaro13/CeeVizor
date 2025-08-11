// 03_stdout_concat.c
#include <stdio.h>

int main(void) {
  printf("A");         // 개행 없음
  printf("B\n");       // 여기서 A와 B가 함께 한 토큰으로 붙어야 함
  puts("C line");      // 무조건 개행
  putchar('D');        // 개행 없음
  putchar('\n');       // 여기서 D가 붙음
  return 0;
}
