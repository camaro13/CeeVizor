import React, { useRef, useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import './App.css';
import stepsData from './steps.json';
import CodeMirror from '@uiw/react-codemirror';
import { cpp } from '@codemirror/lang-cpp';
import { EditorView, Decoration, DecorationSet, ViewPlugin, ViewUpdate } from '@codemirror/view';


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


function findCurrentLineNumber(steps, stepIndex, code) {
  if (!steps[stepIndex]) return null;

  // line_index가 있으면 바로 사용
  if (typeof steps[stepIndex].line_index === 'number') {
    return steps[stepIndex].line_index + 1; // 0-based → 1-based
  }

  //👸현송 : 이부분도 보완
  // 기존 방식: line 텍스트로 찾기
  // line 문자열 매칭(임시 방편): 동일한 줄 텍스트를 찾아서 1-based 인덱스 반환
  if (steps[stepIndex].line) {
    const currentLineText = (steps[stepIndex].line || '').trim();
    const lines = (code || '').split('\n');
    const idx = lines.findIndex(l => l.trim() === currentLineText);
    if (idx >= 0) return idx + 1; // 1-based
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
    setCode('');                     // 코드 입력창 비우기
    setAccumulatedOutput('');        // 출력 누적 비우기
    setError('');                    // 에러 메시지 제거
    setStepIndex(0);                 // 인덱스 초기화
    setSteps([]);                    // 메모리 박스들 비우기 (fallback로 빈 상태 렌더됨)

    // 4) 깜빡임/삭제 관련 상태도 안전하게 초기화 (화면 깔끔)
    setBlinkOn(true);
    setBlinkStackFrameIdxs(new Set());
    setBlinkHeapLabels(new Set());
    setBlinkDataGraph(false);
    setDeletingStackIdxs(new Set());
    setDeletingHeapLabels(new Set());
    setDeletingData(false);
    setDeletedDataKeys(new Set());

    // 5) 메시지는 1.2초 정도 보여주고 자동 숨김
    setTimeout(() => setShowResetMessage(false), 1200);
  };

  
  // JSON 데이터 초기 로드 (첫 단계 데이터 비우기)
  useEffect(() => {
    fetch('/data/sample.json')
      .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then(json => {
        if (Array.isArray(json) && json.length > 0) {
          json[0].memory.data_segment = {};
        }
        setSteps(Array.isArray(json) ? json : []);
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
    const indices = [];
    for (let i = nextLen; i < currLen; i++) indices.push(i);
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
      setBlinkDataGraph(false);
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
  }, [stepIndex, steps]);

  // 전체 실행 핸들러
  const handleRun = () => {
    setSteps(stepsData);
    setStepIndex(0);
    setAccumulatedOutput("");
    let current = 0;
    intervalRef.current && clearInterval(intervalRef.current);
    intervalRef.current = setInterval(() => {
      current++;
      if (current >= stepsData.length) {
        clearInterval(intervalRef.current);
        blinkRef.current && clearInterval(blinkRef.current);
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

  // Stack 시각화 컴포넌트
  function CustomStackGraph({ stack }) {
    if (!stack || stack.length === 0) return null;
    return (
      <div className="stack-graph">
        {stack.map((frame, idx) => {
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
      // 삭제 애니메이션 1초(1000ms) 동안 보여주고 그 후에 상자 숨김
      setShow(true);
      deleteTimeout.current = setTimeout(() => setShow(false), 1000);
    } else {
      // 삭제 중이 아닌 경우 무조건 보여줌
      setShow(true);
      if (deleteTimeout.current) clearTimeout(deleteTimeout.current);
    }
    return () => {
      if (deleteTimeout.current) clearTimeout(deleteTimeout.current);
    };
  }, [deletingData]);

  if (!show || !data || Object.keys(data).length === 0) return null;

  let className = "data-graph";
  if (blinkDataGraph && blinkOn) className += " blink";
  if (deletingData && blinkOn) className += " delete-blink";

  return (
    <div className={className}>
      {Object.entries(data).map(([key, value], i) => (
        <div className="data-variable" key={i}>
          {key} = {value}
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
            <CodeMirror
              value={code}
              height="52vh"
              extensions={[
                cpp(),
                cmView ? highlightLine(findCurrentLineNumber(steps, stepIndex, code), cmView.state.doc) : []
              ]}
              onCreateEditor={(view) => setCmView(view)}
              onChange={(value) => setCode(value)}
            />
          </div>
          <div className="button-container">
            <div className="top-buttons">
              <button onClick={() => alert('한 줄 실행은 나중에 연결 예정입니다.')}>한 줄 실행</button>
              <button onClick={handleRun} disabled={loading}>전체 실행</button>
            </div>
            <button className="full-width-btn" onClick={() => window.location.reload()}>
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
                    {stepIndex > 0 && Object.keys(currentStep.memory.data_segment || {}).length > 0 && (
                      <CustomDataGraph
                        data={currentStep.memory.data_segment}
                        blinkDataGraph={blinkDataGraph}
                        blinkOn={blinkOn}
                        deletingData={deletingData}  // 추가
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
                    {/*👸현송 : 출력결과 메시지 디테일 수정 */}
                    {/* 초기화 메시지: 리셋 직후에만 표시 */}
                    {!loading && !error && showResetMessage && ('초기화 되었습니다.')}

                    {/* 출력이 있으면 출력 표시 */}
                    {!loading && !error && !showResetMessage && accumulatedOutput && (accumulatedOutput || '(출력 없음)')}

                    {/* 아무 것도 없으면 안내 문구 */}
                    {!loading && !error && !showResetMessage && !accumulatedOutput && ('실행버튼을 눌러주세요.')}
                  </div>
                </div>
              </div>

            </div>
          </div>
        </div>

      </div>
      <div className="footer">
        <div className="bottom-divider"></div>
        <img className="hci-logo" src="/hci_logo.png" alt="HCI Logo" />
      </div>
    </div>
  );
}

export default App;
