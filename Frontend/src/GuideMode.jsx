import React, { useRef, useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import './App.css';
import CodeMirror from '@uiw/react-codemirror';
import { cpp } from '@codemirror/lang-cpp';
import { EditorView, Decoration, DecorationSet, ViewPlugin, ViewUpdate } from '@codemirror/view';

// 👸현송 : json 데이터에서 단계 정보를 정규화하는 함수
// 줄 번호 통일, stack 객체 → [{ function, variables }], heap, data → data_segment ㅇ
// 이 함수는 steps.json 파일의 각 단계 데이터를 정규화하여 일관된 형식으로 변환
function normalizeStep(raw) {
  // 줄 번호 통일
  const lineNumber =
    typeof raw.line_index === 'number' ? raw.line_index + 1 :
    typeof raw.line_num === 'number' ? raw.line_num : null;

  // stack: 객체 → [{ function, variables }]
  const stackObj = raw.memory?.stack ?? raw.stack ?? {};
  const stackFrames = Object.entries(stackObj).map(([funcName, varsObj]) => {
    const variables = {};
    Object.entries(varsObj || {}).forEach(([varName, v]) => {
      if (v && typeof v === 'object' && 'value' in v) {
        variables[varName] = v.value;
      } else {
        variables[varName] = v;
      }
    });
    return { function: funcName, variables };
  });

  // heap
  const heapRaw = raw.memory?.heap ?? raw.heap ?? [];
  const heap = Array.isArray(heapRaw) ? heapRaw : [];

  // data → data_segment
  const dataRaw = raw.memory?.data_segment ?? raw.data ?? {};
  const data_segment = Array.isArray(dataRaw)
    ? Object.fromEntries(dataRaw.map(([k, v]) => [k, v]))
    : (dataRaw || {});

  return {
    time: raw.time ?? null,
    line: raw.line ?? '',
    lineNumber,
    memory: {
      stack: stackFrames,
      heap,
      data_segment,
    },
    // ♥현송 : json 파일에서 output이 stdouㅅ으로 되어있길래 그것도 지원가능하도록 추가
    output: raw.output ?? raw.stdout ?? '',
  };
}

  

// 👸현송 : json 전체 배열을 변환
function normalizeSteps(json) {
  if (!Array.isArray(json)) return [];
  return json.map(normalizeStep);
}


//👸현송 : 이 부분 때문에 실행이 안되어 가지고 좀 보완하겠습니다.
// 존재하는 줄이 있을 때만 하이라이팅 하도록 보완
function highlightLine(view, lineNumber) {
  // 객체/값이 없으면 확장 추가하지 않음
  if (!view || !Number.isInteger(lineNumber)) return [];

  const lines = view.state.doc.lines; // 문서 총 줄수
  // 범위를 벗어나면 확장 추가하지 않음 (여기서 막아주니 RangeError 발생 안함)
  if (lineNumber < 1 || lineNumber > lines) return [];

  const line = view.state.doc.line(lineNumber); // 1-based 인덱스
  const deco = Decoration.set([
    Decoration.line({ attributes: { class: 'current-line' } }).range(line.from)
  ]);
  return [EditorView.decorations.of(deco)];
}

// 특정 줄의 위치 계산
function updateLinePos(lineNumber) {
  return { from: 0, to: 0, line: lineNumber - 1 }; // 0-based index
}

function App() {

// 현송 : 하이라이팅 기능 활성화
//  FIX: 하이라이트할 현재 라인 계산 (step 안전 정의 + lineNumber 지원)
function findCurrentLineNumber(steps, stepIndex, code) {
  const step = Array.isArray(steps) ? steps[stepIndex] : null; // ✅ FIX: step 안전하게 정의
  if (!step) return null;

  // raw 형식(line_index: 0-based)도 처리
  if (typeof step.line_index === 'number') return step.line_index + 1;

  // FIX: normalizeStep()가 만든 1-based lineNumber도 처리
  if (typeof step.lineNumber === 'number') return step.lineNumber;

  // 기존: line 문자열 매칭
  if (step.line) {
    const currentLineText = (step.line || '').trim();
    const lines = (code || '').split('\n');
    const idx = lines.findIndex(l => l.trim() === currentLineText);
    if (idx >= 0) return idx + 1;
  }

  return null;
}



  // 기본 상태
  const [cmView, setCmView] = useState(null);
  const [steps, setSteps] = useState([]);
  const [code, setCode] = useState('');
  const [infoVisible, setInfoVisible] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [showResetMessage, setShowResetMessage] = useState(false); // 👸현송 : 초기화 메시지 표시 여부
  // 현송 :  상태 추가 / 메시지창 & 메모리영역 바로실행되는 거 문제 해결을 위한 상태들
  const [loadedSteps, setLoadedSteps] = useState([]);  // 로드만 해두는 원본
  const [isRunning, setIsRunning] = useState(false);   // 실행 중 여부
  const [modalOpen, setModalOpen] = useState(false);   // 경고 모달
  const [modalMsg, setModalMsg] = useState('');        // 모달 메시지
  


  // 기능 상태 (깜빡임, 삭제 등)
  const [stepIndex, setStepIndex] = useState(0);
  const [blinkOn, setBlinkOn] = useState(true);
  const [blinkStackFrameIdxs, setBlinkStackFrameIdxs] = useState(new Set());
  const [blinkHeapLabels, setBlinkHeapLabels] = useState(new Set());
  const [blinkDataGraph, setBlinkDataGraph] = useState(false);
  const [deletingStackIdxs, setDeletingStackIdxs] = useState(new Set());
  const [deletingHeapLabels, setDeletingHeapLabels] = useState(new Set());
  const [deletingData, setDeletingData] = useState(false);
  const [deletedDataKeys, setDeletedDataKeys] = useState(new Set()); // 데이터 삭제 대상 키 저장
  const [accumulatedOutput, setAccumulatedOutput] = useState("");

  const inputRef = useRef(null);
  const lineRef = useRef(null);
  const intervalRef = useRef();
  const blinkRef = useRef();
  const openWarn = (msg) => { setModalMsg(msg); setModalOpen(true); }; //현송 : 경고 모달 열기 함수



  
  //👸현송 : cmView/steps/stepIndex/code가 바뀔 때마다 안전하게 확장을 만든 뒤 전달 추가
  // CodeMirror extensions를 안전하게 구성
  const cmExtensions = useMemo(() => {
    // 기본 확장: C/C++ 문법 하이라이트
    const basic = [cpp()];

    // 아직 view가 없으면 기본만
    if (!cmView) return basic;

    // 현재 하이라이트할 줄 번호(1-based) 계산
    const ln = findCurrentLineNumber(steps, stepIndex, code);

    // 존재하는 줄일 때만 하이라이트 확장 추가
    return basic.concat(highlightLine(cmView, ln));
  }, 
  [cmView, steps, stepIndex, code]);

  //👸현송 : 초기화 함수 기능 추가
  const handleResetClick = () => {
    // 1) 진행 중인 인터벌/블링크 타이머 정리
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    if (blinkRef.current) {
      clearInterval(blinkRef.current);
      blinkRef.current = null;
    }
    // 2) 출력창에 메시지 표시
    setShowResetMessage(true);

    // 3) 시각화와 코드 상태 초기화
    setAccumulatedOutput('');        // 출력 누적 비우기
    setError('');                    // 에러 메시지 제거
    setStepIndex(0);                 // 인덱스 초기화
    setSteps([]);                    // 메모리 박스들 비우기 (fallback로 빈 상태 렌더됨)

    // 4) 깜빡임/삭제 관련 상태도 안전하게 초기화 (화면 깔끔)
    setBlinkOn(false);
setTimeout(() => {
  setBlinkOn(true);
}, 50);
    setBlinkStackFrameIdxs(new Set());
    setBlinkHeapLabels(new Set());
    setBlinkDataGraph(false);
    setDeletingStackIdxs(new Set());
    setDeletingHeapLabels(new Set());
    setDeletingData(false);
    setDeletedDataKeys(new Set());

    setIsRunning(false); // 실행 중 상태 해제
    setSteps([]); // steps 상태 초기화
    setStepIndex(0);// 초기화 후에는 실행 전 상태로
    setTimeout(() => setShowResetMessage(false), 2500); // 2.5초 후 메시지 숨김

  };

  // 👸현송 : json 테스트 파일이 여러개라 바로바로 테스트할 수 있도록 기능 추가 
  // 현송 : ++ .json 파일 변환해서 저장하는 명령어 추가
const handleJsonChange = (e) => {
  const fileName = e.target.value;
  setSelectedFile(fileName);
  fetch(`/data/${fileName}`)
    .then(res => res.json())
    .then(json => setLoadedSteps(normalizeSteps(json))) // 현송 : 드롭다운 변경도 steps 말고 loadedSteps만 갱신
    .catch(err => setError('JSON 파일 인식 실패: ' + err.message));
};
    
  // JSON 데이터 초기 로드 (첫 단계 데이터 비우기)
  useEffect(() => {
    fetch('/data/test.json')
      .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })

      // 👸현송 : 바로 메모리영역 실행되는거 수정
      .then(json => {
          const normalized = normalizeSteps(json);
          // 초기에는 실행 전 상태로 보관만

          setLoadedSteps(normalized);
          setSteps([]);         // ★ 실행 전에는 비워둠
          setStepIndex(0);
          setIsRunning(false);
        })
      
      .catch(err => setError('json 파일 로드 실패: ' + err.message))
      .finally(() => setLoading(false));
  }, []);


  // 각종 깜빡임 및 삭제 대상 계산 함수 (스택, 힙, 데이터)
  function blinkStackFrames(prev, curr) {
    const prevMap = {};
    (prev || []).forEach((frame, idx) => {
      prevMap[idx] = {};
      Object.entries(frame.variables || {}).forEach(([key, value]) => { prevMap[idx][key] = value; });
    });
    const blinkIdxs = [];
    (curr || []).forEach((frame, idx) => {
      const prevVars = prevMap[idx] || {};
      const changed = Object.entries(frame.variables || {}).some(([key, value]) => {
        if (typeof value === "string" && /^0x[0-9a-f]+$/i.test(value)) return false;
        return !(key in prevVars) || prevVars[key] !== value;
      });
      if (changed) blinkIdxs.push(idx);
    });
    return new Set(blinkIdxs);
  }

  function blinkHeapBlocks(prev, curr) {
  const prevMap = {};
  (prev || []).forEach(block => {
    let label, value;
    if ('address' in block && 'value' in block) {
      label = block.address;
      value = block.value;
    } else {
      [label, value] = Object.entries(block)[0];
    }
    prevMap[label] = value;
  });

  const blinkLabels = [];
  (curr || []).forEach(block => {
    let label, value;
    if ('address' in block && 'value' in block) {
      label = block.address;
      value = block.value;
    } else {
      [label, value] = Object.entries(block)[0];
    }
    if (!(label in prevMap) || prevMap[label] !== value) {
      blinkLabels.push(label);
    }
  });

  return new Set(blinkLabels);
}
  function blinkData(prev, curr) {
    if (JSON.stringify(prev) === JSON.stringify(curr)) return false;
    const prevMap = {};
    Object.entries(prev || {}).forEach(([key, value]) => { prevMap[key] = value; });
    return Object.entries(curr || {}).some(([key, value]) => !(key in prevMap) || prevMap[key] !== value);
  }

  function deletedStackFrames(curr, next) {
    const currLen = (curr || []).length;
    const nextLen = (next || []).length;
    if (nextLen >= currLen) return new Set();
    // 현송 :새프레임이 아래에 생기지 않도록 수정 ( curr의 마지막 인덱스부터 삭제)
    const indices = [];
    for (let i = currLen - 1; i >= nextLen; i--) {
      indices.push(i);
    }
    return new Set(indices);
  }

  function deletedHeapBlocks(curr, next) {
    const nextLabels = new Set((next || []).map(block => Object.keys(block)[0]));
    return new Set((curr || []).map((block, idx) => {
      const label = Object.keys(block)[0];
      return !nextLabels.has(label) ? idx : null;
    }).filter(i => i !== null));
  }

  // 단계 변경 시 상태 업데이트 (깜빡임, 삭제 등)
  useEffect(() => {
    if (!steps.length) return;

    const currentStack = steps[stepIndex]?.memory?.stack || [];
    const emptyFrameIdxs = new Set();
    currentStack.forEach((frame, idx) => {
      const filteredVariables = {};
      Object.entries(frame.variables || {}).forEach(([key, value]) => {
        if ((typeof value === "string" && /^0x[0-9a-f]+$/i.test(value)) || value === null) return;
        filteredVariables[key] = value;
      });
      if (Object.keys(filteredVariables).length === 0) emptyFrameIdxs.add(idx);
    });

    let blinkStackIdxs = stepIndex === 0
      ? blinkStackFrames([], currentStack)
      : blinkStackFrames(steps[stepIndex - 1]?.memory?.stack, currentStack);
    emptyFrameIdxs.forEach(idx => blinkStackIdxs.delete(idx));
    setBlinkStackFrameIdxs(blinkStackIdxs);

    setBlinkHeapLabels(blinkHeapBlocks(
      stepIndex === 0 ? [] : steps[stepIndex - 1]?.memory?.heap,
      steps[stepIndex]?.memory?.heap
    ));

    if (stepIndex === 0) {
      setBlinkDataGraph(true);
    } else {
      const prevData = stepIndex === 1 ? {} : steps[stepIndex - 1]?.memory?.data_segment;
      setBlinkDataGraph(blinkData(prevData, steps[stepIndex]?.memory?.data_segment));
    }

    if (stepIndex < steps.length - 1) {
      setDeletingStackIdxs(deletedStackFrames(
        steps[stepIndex]?.memory?.stack,
        steps[stepIndex + 1]?.memory?.stack
      ));
      setDeletingHeapLabels(deletedHeapBlocks(
        steps[stepIndex]?.memory?.heap,
        steps[stepIndex + 1]?.memory?.heap
      ));

      // Data 삭제될 키 계산 및 저장
      const currKeys = new Set(Object.keys(steps[stepIndex]?.memory?.data_segment || {}));
      const nextKeys = new Set(Object.keys(steps[stepIndex + 1]?.memory?.data_segment || {}));
      const deletedKeys = [...currKeys].filter(k => !nextKeys.has(k));
      setDeletedDataKeys(new Set(deletedKeys));
      setDeletingData(deletedKeys.length > 0);
    } else {
      setDeletingStackIdxs(new Set());
      setDeletingHeapLabels(new Set());
      setDeletingData(false);
      setDeletedDataKeys(new Set());
    }

    setBlinkOn(true);
    blinkRef.current && clearInterval(blinkRef.current);
    blinkRef.current = setInterval(() => setBlinkOn(v => !v), 500);

    return () => {
      blinkRef.current && clearInterval(blinkRef.current);
    };
  }, [stepIndex, steps]);

  // 출력 누적
  useEffect(() => {
    if (!steps.length) return;
    const newLine = steps[stepIndex]?.output || "";
    if (newLine) {
      setAccumulatedOutput(prev => prev + newLine + "\n");
    }
    console.log("current output:", newLine) // 0816 현송  : 제대로 찍히는지 일단 화긴 
  }, [stepIndex, steps]);

  // 전체 실행 핸들러
  // 현송 : 코드 입력창이 비어있거나 실행할 단계 데이터가 없을 때 경고 메시지 표시
  const handleRun = () => {
    if (!code.trim()) {
      openWarn('코드를 입력한 뒤 실행해주세요.');
      return;
    }
    const data = loadedSteps.length ? loadedSteps : stepsData;
    if (!data.length) {
      openWarn('실행할 단계 데이터가 없습니다.');
      return;
    }

    // 기존 자동실행 타이머가 있으면 먼저 정지
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }

    setIsRunning(true);  
    setSteps(data);
    setStepIndex(0);
    setAccumulatedOutput("");

        let current = 0;
          clearInterval(intervalRef.current);

          intervalRef.current = setInterval(() => {
            current++;
            if (current >= data.length) {
              clearInterval(intervalRef.current);

              // ★★★ 실행 끝났을 때 삭제 애니메이션 트리거 ★★★
              const lastStep = data[data.length - 1];

              // Stack
              if ((lastStep.memory.stack || []).length > 0)
                setDeletingStackIdxs(new Set(
                  (lastStep.memory.stack || []).map((_, idx) => idx)
                ));
              // Data
              if (Object.keys(lastStep.memory.data_segment || {}).length > 0)
                setDeletingData(true);
              // Heap
              if ((lastStep.memory.heap || []).length > 0)
                setDeletingHeapLabels(new Set(
                  (lastStep.memory.heap || []).map((_, idx) => idx)
                ));

              setBlinkOn(true);

      // 일정 시간 후 완전히 삭제
      setTimeout(() => {
        setSteps([]); // 모든 영역 비움
        setDeletingStackIdxs(new Set());
        setDeletingData(false);
        setDeletingHeapLabels(new Set());
      }, 3000);
      // ★★★ 여기까지 실행 끝나고 정리! ★★★
    } else {
      setStepIndex(current);
    }
  }, 3000);
};

  const navigate = useNavigate();

  const handleScroll = () => {
    if (inputRef.current && lineRef.current) {
      lineRef.current.scrollTop = inputRef.current.scrollTop;
    }
  };

  const generateLineNumbers = () => {
    const lineCount = Math.max(code.split('\n').length, 20);
    return Array.from({ length: lineCount }, (_, i) => (
      <div className="line-number" key={i}>{String(i + 1).padStart(2, '0')}</div>
    ));
  };

  const toggleInfo = (type) => {
    setInfoVisible(prev => prev === type ? null : type);
  };

// 현송 : 전체, 한줄 버튼 시간 꼬이는 거 수정 코드 
const handleStepOnce = () => {
  const data = loadedSteps.length ? loadedSteps : stepsData;
  const lastStep = data[data.length - 1];
  if (!code.trim()) {
    openWarn('코드를 입력한 뒤 실행해주세요.');
    return;
  }
  if (!data.length) {
    openWarn('실행할 단계 데이터가 없습니다.');
    return;
  }

  // 자동실행 중이면 먼저 정지하고 수동 모드로 전환
  if (intervalRef.current) {
    clearInterval(intervalRef.current);
    intervalRef.current = null;
  }

  // 아직 세션 시작 안 됐으면 초기 세팅(0번째 스텝으로 진입)
  if (!steps.length) {
    setIsRunning(true);
    setSteps(data);
    setStepIndex(0);
  } else {
    setStepIndex(i => {
      const nextIndex = Math.min(i + 1, data.length - 1);
      if (nextIndex === data.length - 1) {
        setDeletingData(true);
        if ((lastStep.memory.stack || []).length > 0) {
          setDeletingStackIdxs(new Set(lastStep.memory.stack.map((_, idx) => idx)));
        }
        if ((lastStep.memory.heap || []).length > 0) {
          setDeletingHeapLabels(new Set(lastStep.memory.heap.map((_, idx) => idx)));
        }
        setBlinkOn(false);           // 깜빡임 초기화
        setTimeout(() => setBlinkOn(true), 50); // 약간의 딜레이 후 다시 켜기
        setTimeout(() => {
          setDeletingData(false);
          setDeletingStackIdxs(new Set());
          setDeletingHeapLabels(new Set());
          setSteps([]);
          setIsRunning(false);
          setStepIndex(0);
        }, 3000);
      }
      return nextIndex;
    });
  }
};



  // Stack 시각화 컴포넌트
  // 현송 : 백앤드에서 넘겨주는 데이터는 main -> 호출된 함수 순으로 아래로 쌓이는 구조라, map 돌리기 전에 reverse()g해서 위쪽으로 생기게 변경
function CustomStackGraph({ stack }) {
  if (!stack || stack.length === 0) return null;
  return (
    <div className="stack-graph">
      {[...stack].map((frame, revIdx) => {
        const idx = stack.length - 1 - revIdx; // 원래 인덱스 (깜빡임, 삭제 체크할 때 필요)
        const filteredVariables = {};
        Object.entries(frame.variables || {}).forEach(([key, value]) => {
          if ((typeof value === "string" && /^0x[0-9a-f]+$/i.test(value)) || value === null) return;
          filteredVariables[key] = value;
        });
        const isEmpty = Object.keys(filteredVariables).length === 0;

        let className = "stack-frame";
        if (!isEmpty && blinkStackFrameIdxs.has(idx) && blinkOn) className += " blink";
        if (!isEmpty && deletingStackIdxs.has(idx) && blinkOn) className += " delete-blink";
        if (isEmpty) className += " empty-frame";
        if (isEmpty) return null;

        return (
          <div className={className} key={idx}>
            <div className="stack-variable-container">
              {Object.entries(filteredVariables).map(([key, value], i) => (
                <div className="stack-variable" key={i}>{key} = {String(value)}</div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}


  // Heap 시각화 컴포넌트
function CustomHeapGraph({ heap, stack }) {
  if (!heap || heap.length === 0) return null;

  const addrToVarName = {};
  (stack || []).forEach(frame => {
    if (!frame.variables) return;
    Object.entries(frame.variables).forEach(([varName, val]) => {
      if (typeof val === 'string' && /^0x[0-9a-f]+$/i.test(val)) {
        addrToVarName[val] = varName;
      }
    });
  });

  return (
    <div className="heap-graph">
      {heap.map((block, idx) => {
        let addr, val;
        if ('address' in block && 'value' in block) {
          addr = block.address;
          val = block.value;
        } else {
          [addr, val] = Object.entries(block)[0];
        }

        const displayName = addrToVarName[addr] || addr;
        let className = "heap-block";
        // blinkHeapLabels는 addr 값 그대로를 써야 이전/현재 비교가 일치함
        if (blinkHeapLabels.has(addr) && blinkOn) className += " blink";
        if (deletingHeapLabels.has(idx) && blinkOn) className += " delete-blink";
        return (
          <div className={className} key={idx}>
            {displayName} = {val !== null ? String(val) : 'null'}
          </div>
        );
      })}
    </div>
  );
}

  // Data 시각화 컴포넌트 수정: 삭제될 key만 delete-blink 클래스 부여
function CustomDataGraph({ data, blinkDataGraph, deletingData, blinkOn }) {
  const [show, setShow] = useState(true);
  const deleteTimeout = useRef();

  useEffect(() => {
    if (deletingData) {
      setShow(true);
      
      // 3초 후에 데이터 영역 감추기
      deleteTimeout.current = setTimeout(() => setShow(false), 3000);
    } else {
      setShow(true);
      if (deleteTimeout.current) clearTimeout(deleteTimeout.current);
    }
    return () => {
      if (deleteTimeout.current) clearTimeout(deleteTimeout.current);
    };
  }, [deletingData]);

  // Data 영역을 숨길 조건 (삭제 애니메이션 후 사라짐)
  if (!show || !data || Object.keys(data).length === 0) return null;

  // 클래스명 처리 (blink, delete-blink)
  let className = "data-graph";
  if (blinkDataGraph && blinkOn) className += " blink";
  if (deletingData && blinkOn) className += " delete-blink";

  // 데이터 글로벌 변수만 순회하여 렌더링
  return (
    <div className={className}>
      {data.global && Object.entries(data.global).map(([key, v], i) => (
        <div className="data-variable" key={i}>
          {
              v.type === 'char' && /^\w+\[\d+\]$/.test(v.name)
                ? `char ${v.name} = "${v.value.replace(/^"|"$/g, '')}"`
                : `${v.type || ''} ${v.name} = ${v.value}`
            }
        </div>
      ))}
    </div>
  );
}


  const currentStep = steps[stepIndex] || { memory: { stack: [], heap: [], data_segment: {} }, output: '', line: '', line_index: '' };

  return (
    <div className="app-wrapper">
      <div className="container">

        <button onClick={() => navigate('/')} className="back-button">메인화면으로</button>

        <div className="left-panel">
          <h2>코드입력창</h2>
          <div className="scrollable-container">
            <div className="line-numbers" ref={lineRef}>
            </div>
              {/* 현송 : 코드입력창 약간 수정 */}
              {/* AFTER (FIX: memo된 cmExtensions 그대로 전달) */}
              <CodeMirror
                value={`#include <stdio.h>
#include <stdlib.h>
// 위 비행기 아이디어 기반 간단 흐름 코드

int flight_number = 1234; // 데이터 영역

int* load_cargo() {
    int* box = malloc(sizeof(int));
    *box = 42;
    return box;
}

void passenger_boarding(int ticket) {
    int seat = ticket + 1;
    int* cargo = load_cargo();
    printf("Seat: %d\\n", seat);
    printf("Cargo content: %d\\n",*cargo);
    free(cargo);
}

int main() {
    passenger_boarding(flight_number);
    return 0;
}`}
                height="52vh"
                extensions={cmExtensions}              // 여기 FIX

                /*준혁 : 코드 수정 불가 */
                editable={false}
                
                onCreateEditor={(view) => setCmView(view)}
                onChange={(value) => setCode(value)}
              />
          </div>
          <div className="button-container">
            <div className="top-buttons">
              <button onClick={handleStepOnce}>한 줄 실행</button>  {/* 현송 : 함수 연결 */}
              <button onClick={handleRun} disabled={loading}>전체 실행</button>
            </div>

            <button className="full-width-btn" onClick={handleResetClick}> 
              시각화 초기화
            </button>
          </div>
        </div>

        <div className="right-panel">
          <h2>메모리 시각화</h2>
          <div className="memory-container">
              <div className="memory-row">
                {/* Stack 영역 */}
                <div className="mem-section no-pointer">
                  <div className="mem-title" style={{ position: 'relative' }}>
                    Stack
                    <img src="/question_mark.png" alt="스택 정보" className="help-icon" onClick={() => toggleInfo('stack')} />
                    {infoVisible === 'stack' && (
                      <div className="info-popup local">
                        <button className="close-btn" onClick={() => setInfoVisible(null)}>×</button>
                        <p><strong>Stack:</strong> 함수 호출 시 자동으로 생성되는 스택프레임들이 저장되는 공간입니다.</p>
                      </div>
                    )}
                  </div>
                  <div className="mem-box">
                    <div className="mem-content stack-area">
                      <CustomStackGraph stack={currentStep.memory.stack} />
                    </div>
                  </div>
                </div>

                {/* Heap 영역 */}
                <div className="mem-section no-pointer">
                  <div className="mem-title" style={{ position: 'relative' }}>
                    Heap
                    <img src="/question_mark.png" alt="힙 정보" className="help-icon" onClick={() => toggleInfo('heap')} />
                    {infoVisible === 'heap' && (
                      <div className="info-popup local">
                        <button className="close-btn" onClick={() => setInfoVisible(null)}>×</button>
                        <p><strong>Heap:</strong> 동적으로 할당된 배열, 구조체 등의 객체들이 저장되는 메모리 영역입니다.</p>
                      </div>
                    )}
                  </div>
                  <div className="mem-box">
                    <div className="mem-content">
                      <CustomHeapGraph heap={currentStep.memory.heap} stack={currentStep.memory.stack} />
                    </div>
                  </div>
                </div>

                {/* Data 영역 */}
                <div className="mem-section no-pointer data-section">
                  <div className="mem-title" style={{ position: 'relative' }}>
                    Data
                    <img src="/question_mark.png" alt="데이터 정보" className="help-icon" onClick={() => toggleInfo('data')} />
                    {infoVisible === 'data' && (
                      <div className="info-popup local">
                        <button className="close-btn" onClick={() => setInfoVisible(null)}>×</button>
                        <p><strong>Data:</strong> 전역 변수 및 정적 변수를 할당하는 영역입니다.</p>
                      </div>
                    )}
                  </div>
                  <div className="mem-box code-box">
                    <div className="mem-content">
                      {stepIndex >= 0 && Object.keys(currentStep.memory.data_segment || {}).length > 0 && (
                        <CustomDataGraph
                          data={currentStep.memory.data_segment}
                          blinkDataGraph={blinkDataGraph}
                          blinkOn={blinkOn}
                          deletingData={deletingData}
                          deletedDataKeys={deletedDataKeys}
                        />
                      )}
                    </div>
                  </div>
                  <div className="output-section pointer-allowed">
                    <div className="mem-title">출력 결과</div>
                    <div className="output-box" style={{ whiteSpace: 'pre-wrap' }}>
                      {loading && '로딩 중...'}
                      {!loading && error && <span style={{ color: '#d33' }}>{error}</span>}
                      {!loading && !error && showResetMessage && ('초기화 되었습니다.')}
                      {!loading && !error && !showResetMessage && accumulatedOutput && (accumulatedOutput || '(출력 없음)')}
                      {!loading && !error && !showResetMessage && !accumulatedOutput && ('실행버튼을 눌러주세요.')}
                    </div>
                  </div>
                </div>
              </div>

            
          </div>
        </div>

      {/* 현송 : 경고 모달 */}
      {modalOpen && (
        <div className="modal-backdrop" onClick={() => setModalOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-title">알림</div>
            <div className="modal-body">{modalMsg}</div>
            <div className="modal-actions">
              <button onClick={() => setModalOpen(false)}>확인</button>
            </div>
          </div>
        </div>
      )}

      </div>
      <div className="footer">
        <div className="bottom-divider"></div>
        <img className="hci-logo" src="/hci_logo.png" alt="HCI Logo" />
      </div>
    </div>
  );
}

export default App;