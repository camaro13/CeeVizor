export function parseCodeToSteps(code) {
  // (입력 code는 무시—고정 예제 전용)
  const steps = [];
  const dataSection = [{ key: 'flight_number', value: 1234 }];

  // 1. main() 진입 (스택에 반드시 main 프레임)
  steps.push({
    stack: [],
    heap: [],
    data: dataSection,
    output: '',
    code: { line: 17, text: 'int main()' }
  });

  // 2. passenger_boarding 호출
  steps.push({
    stack: [
      { function: 'passenger_boarding', variables: [{ key: 'ticket', value: 1234 }] }
    ],
    heap: [],
    data: dataSection,
    output: '',
    code: { line: 10, text: 'void passenger_boarding(int ticket)' }
  });

  // 3. seat 변수 생성
  steps.push({
    stack: [
      { function: 'passenger_boarding', variables: [
        { key: 'ticket', value: 1234 },
        { key: 'seat', value: 1235 }
      ]}
    ],
    heap: [],
    data: dataSection,
    output: '',
    code: { line: 11, text: 'int seat = ticket + 1;' }
  });

  // 4. seat 출력
  steps.push({
    stack: [
      { function: 'passenger_boarding', variables: [
        { key: 'ticket', value: 1234 },
        { key: 'seat', value: 1235 }
      ]}
    ],
    heap: [],
    data: dataSection,
    output: 'Seat: 1235\n',
    code: { line: 12, text: 'printf("Seat: %d\\n", seat);' }
  });

  // 5. load_cargo 호출 (힙, cargo 변수 할당)
  steps.push({
    stack: [
      { function: 'passenger_boarding', variables: [
        { key: 'ticket', value: 1234 },
        { key: 'seat', value: 1235 },
        { key: 'cargo', value: '0x100' }
      ]}
    ],
    heap: [
      { label: 'box', value: 42 }
    ],
    data: dataSection,
    output: 'Seat: 1235\n',
    code: { line: 7, text: 'int* box = malloc(sizeof(int));' }
  });

  // 6. cargo 내용 출력
  steps.push({
    stack: [
      { function: 'passenger_boarding', variables: [
        { key: 'ticket', value: 1234 },
        { key: 'seat', value: 1235 },
        { key: 'cargo', value: '0x100' }
      ]}
    ],
    heap: [
      { label: 'box', value: 42 }
    ],
    data: dataSection,
    output: 'Seat: 1235\nCargo content: 42\n',
    code: { line: 13, text: 'printf("Cargo content: %d\\n", *cargo);' }
  });

  // 7. free(cargo) → 힙의 box 사라짐
  steps.push({
    stack: [
      { function: 'passenger_boarding', variables: [
        { key: 'ticket', value: 1234 },
        { key: 'seat', value: 1235 },
        { key: 'cargo', value: '0x100' }
      ]}
    ],
    heap: [],
    data: dataSection,
    output: 'Seat: 1235\nCargo content: 42\n',
    code: { line: 14, text: 'free(cargo);' }
  });

  // 8. passenger_boarding 종료
  steps.push({
    stack: [],
    heap: [],
    data: dataSection,
    output: 'Seat: 1235\nCargo content: 42\n',
    code: { line: 15, text: 'passenger_boarding() 종료' }
  });

  // 9. main 종료(프로그램 종료) — 마지막에도 dataSection!
  steps.push({
    stack: [],
    heap: [],
    data: [],    // 마지막까지 남기세요 (빈 배열 X)
    output: 'Seat: 1235\nCargo content: 42\n',
    code: { line: 18, text: 'return 0;' }
  });

  return steps;
}
