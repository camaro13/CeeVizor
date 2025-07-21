export function parseCodeToSteps(code) {
  if (!code.trim()) return [];

  const steps = [];
  const arrValues = [1, 2, 3, 4, 5];

  // ✅ 항상 유지되는 Data 영역 전역변수
  const dataSection = [
    { key: 'global_var', value: 100 }
  ];

  // 🧾 스텝 0: main 함수 진입
  steps.push({
    stack: [
      {
        function: 'main',
        variables: [
          { key: 'n', value: 5 }
        ]
      }
    ],
    heap: [],
    output: '',
    code: {
      line: 12,
      text: 'int n = 5;'
    },
    data: dataSection
  });

  // 💡 스텝 1~5: heap_arr 점진적 할당
  for (let i = 0; i < arrValues.length; i++) {
    const heapBlocks = [];
    for (let j = 0; j <= i; j++) {
      heapBlocks.push({ label: `heap_arr[${j}]`, value: arrValues[j] });
    }

    steps.push({
      stack: [
        {
          function: 'main',
          variables: [
            { key: 'heap_arr', value: `[${arrValues.slice(0, i + 1).join(', ')}${i < 4 ? ', ...' : ''}]` },
            { key: 'n', value: 5 }
          ]
        }
      ],
      heap: heapBlocks,
      output: '',
      code: {
        line: 15,
        text: `heap_arr[${i}] = ${i + 1};`
      },
      data: dataSection
    });
  }

  // ✅ 스텝 6: print_sum 진입
  steps.push({
    stack: [
      {
        function: 'main',
        variables: [
          { key: 'heap_arr', value: '[1, 2, 3, 4, 5]' },
          { key: 'n', value: 5 }
        ]
      },
      {
        function: 'print_sum',
        variables: [
          { key: 'sum', value: 0 },
          { key: 'i', value: 0 }
        ]
      }
    ],
    heap: arrValues.map((v, idx) => ({ label: `heap_arr[${idx}]`, value: v })),
    output: '',
    code: {
      line: 6,
      text: 'void print_sum(int *arr, int size) { ... }'
    },
    data: dataSection
  });

  // ⏱️ 스텝 7 ~ 11: 합계 누적 중
  let sum = 0;
  for (let i = 0; i < 5; i++) {
    sum += arrValues[i];

    steps.push({
      stack: [
        {
          function: 'main',
          variables: [
            { key: 'heap_arr', value: '[1, 2, 3, 4, 5]' },
            { key: 'n', value: 5 }
          ]
        },
        {
          function: 'print_sum',
          variables: [
            { key: 'sum', value: sum },
            { key: 'i', value: i + 1 }
          ]
        }
      ],
      heap: arrValues.map((v, idx) => ({ label: `heap_arr[${idx}]`, value: v })),
      output: '',
      code: {
        line: 9,
        text: `sum += arr[${i}];`
      },
      data: dataSection
    });
  }

  // 🖨️ 스텝 12: printf 출력
  steps.push({
    stack: [
      {
        function: 'main',
        variables: [
          { key: 'heap_arr', value: '[1, 2, 3, 4, 5]' },
          { key: 'n', value: 5 }
        ]
      }
    ],
    heap: [],
    output: '합계: 15\n',
    code: {
      line: 10,
      text: 'printf("합계: %d\\n", sum);'
    },
    data: dataSection
  });

  // 🚪 스텝 13: 프로그램 종료
  steps.push({
    stack: [],
    heap: [],
    output: '합계: 15\n',
    code: {
      line: 18,
      text: 'return 0;'
    },
    data: [] // 전역 변수도 해제됨
  });

  return steps;
}
