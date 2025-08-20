// tests_memory_ops.c
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

int g_init = 1;            // .data (초기화된 전역)
int g_zero;                // .bss  (0으로 시작)
char g_msg[8] = "Hi";      // .data (전역 배열)
static int g_file_static;  // .bss  (파일 내부 링크)
volatile int g_vol = 0;    // .data (volatile 전역)

struct Pair { int a; int b; };

void test_auto_and_ops(void) {
    int x = 10;        // 자동 변수 (스택)
    x = x + 1;         // 단순 대입 (쓰기)
    x += 2;            // 복합 대입 (쓰기)
    x *= 3;            // 복합 대입 (쓰기)
    ++x;               // 전위 증감 (쓰기)
    x--;               // 후위 감소 (쓰기)
    g_init = x;        // 전역 쓰기
    g_zero++;          // 전역 쓰기(++)

    (void)g_file_static; // 사용 표식(최적화 방지 목적)
}

void test_static_local(void) {
    static int s;      // 정적 지역(.bss), 프로그램 전 기간 유지
    s++;               // 정적 지역 쓰기
    g_init += s;       // 전역 쓰기(+=)
}

void test_pointer_and_array(void) {
    int arr[3] = {10, 20, 30};
    int *p = arr;      // p 값(주소) 변경
    p = p + 1;         // 포인터 산술(주소만 변경)
    (*p)++;            // 역참조 쓰기: arr[1]이 21이 됨
    arr[0] += 1;       // 배열 원소 쓰기

    char *m = g_msg;   // 전역 배열을 가리키는 포인터
    m = m + 1;         // 포인터 산술
    *m = 'e';          // "Hi" -> "He"
}

void test_heap(void) {
    int *hp = (int*)malloc(sizeof *hp); // malloc 할당(힙)
    if (!hp) return;
    *hp = 42;           // 힙 블록 쓰기
    *hp = *hp + 1;      // 힙 블록 쓰기(43)
    free(hp);           // 해제
}

void test_mem_functions(void) {
    char buf[16];
    memset(buf, 0, sizeof buf);     // 버퍼 0으로 채움
    memset(buf, 'A', 4);            // "AAAA"
    memcpy(buf + 4, "OK", 3);       // "AAAAOK\0"
    memmove(buf + 1, buf, 6);       // 겹침 복사 (쓰기 발생)
    g_msg[0] = buf[0];              // 전역 배열 첫 글자 갱신
}

void test_struct_and_ptr(void) {
    struct Pair s = {1, 2};         // 구조체 로컬
    struct Pair t;                   // 구조체 대입은 바이트 단위 복사
    t = s;                           // 구조체 대입(쓰기)
    int *pa = &t.a;                  // 구조체 필드 주소
    *pa = 7;                         // 포인터 역참조로 구조체 필드 쓰기
}

void test_volatile(void) {
    g_vol = 123;                     // volatile 전역 쓰기(실제 메모리 접근)
    volatile int *reg = &g_vol;      // volatile 포인터
    *reg = *reg + 1;                 // volatile 위치에 쓰기(124)
}

int main(void) {
    test_auto_and_ops();
    test_static_local();
    test_static_local();             // 두 번 호출해서 static 지역 누적 확인
    test_pointer_and_array();
    test_heap();
    test_mem_functions();
    test_struct_and_ptr();
    test_volatile();

    // 시뮬레이터의 출력 매핑(printf) 테스트용
    printf("g_init=%d g_zero=%d g_msg=\"%s\" g_vol=%d\n",
           g_init, g_zero, g_msg, g_vol);
    return 0;
}
