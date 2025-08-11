import React, { useRef, useState, useEffect } from 'react';
import './App.css';
import stepsData from './steps.json';

// 기존 컴포넌트 import 유지
import StackGraph from './components/StackGraph';
import HeapGraph from './components/HeapGraph';
import DataGraph from './components/DataGraph';

function App() {
  const [code, setCode] = useState('');
  const [steps, setSteps] = useState([]); // 초기값 빈 배열
  const [stepIndex, setStepIndex] = useState(0);

  const [blinkOn, setBlinkOn] = useState(true);
  const [blinkStackFrameIdxs, setBlinkStackFrameIdxs] = useState(new Set());
  const [blinkHeapLabels, setBlinkHeapLabels] = useState(new Set());
  const [blinkDataGraph, setBlinkDataGraph] = useState(false);

  const [deletingStackIdxs, setDeletingStackIdxs] = useState(new Set());
  const [deletingHeapLabels, setDeletingHeapLabels] = useState(new Set());
  const [deletingData, setDeletingData] = useState(false);

  const [accumulatedOutput, setAccumulatedOutput] = useState("");  // 출력 누적 상태 추가

  const inputRef = useRef(null);
  const lineRef = useRef(null);
  const intervalRef = useRef();
  const blinkRef = useRef();

  // 기존 blink/delete 계산 함수는 그대로 유지 (생략)

  function blinkStackFrames(prev, curr) {
    const prevMap = {};
    (prev || []).forEach((frame, idx) => {
      prevMap[idx] = {};
      Object.entries(frame.variables || {}).forEach(([key, value]) => {
        prevMap[idx][key] = value;
      });
    });

    const blinkIdxs = [];
    (curr || []).forEach((frame, idx) => {
      const prevVars = prevMap[idx] || {};

      const changed = Object.entries(frame.variables || {}).some(([key, value]) => {
        if (typeof value === "string" && /^0x[0-9a-f]+$/i.test(value)) {
          return false;
        }
        return !(key in prevVars) || prevVars[key] !== value;
      });

      if (changed) blinkIdxs.push(idx);
    });

    return new Set(blinkIdxs);
  }

  function blinkHeapBlocks(prev, curr) {
    const prevMap = {};
    (prev || []).forEach(block => {
      const [label, value] = Object.entries(block)[0];
      prevMap[label] = value;
    });

    const blinkLabels = [];
    (curr || []).forEach(block => {
      const [label, value] = Object.entries(block)[0];
      if (!(label in prevMap) || prevMap[label] !== value) {
        blinkLabels.push(label);
      }
    });

    return new Set(blinkLabels);
  }

  function blinkData(prev, curr) {
    const prevMap = {};
    Object.entries(prev || {}).forEach(([key, value]) => { prevMap[key] = value; });
    return Object.entries(curr || {}).some(([key, value]) =>
      !(key in prevMap) || prevMap[key] !== value
    );
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
    const deleted = (curr || []).map((block, idx) => {
      const label = Object.keys(block)[0];
      return !nextLabels.has(label) ? idx : null;
    }).filter(i => i !== null);
    return new Set(deleted);
  }

  function deletedData(curr, next) {
    const nextKeys = new Set(Object.keys(next || {}));
    return Object.keys(curr || {}).some(key => !nextKeys.has(key));
  }

  useEffect(() => {
    if (!steps.length) return;

    const currentStack = steps[stepIndex]?.memory?.stack || [];

    const emptyFrameIdxs = new Set();
    currentStack.forEach((frame, idx) => {
      const filteredVariables = {};
      Object.entries(frame.variables || {}).forEach(([key, value]) => {
        if (
          (typeof value === "string" && /^0x[0-9a-f]+$/i.test(value)) ||
          value === null
        ) return;
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

    setBlinkDataGraph(blinkData(
      stepIndex === 0 ? {} : steps[stepIndex - 1]?.memory?.data_segment,
      steps[stepIndex]?.memory?.data_segment
    ));

    if (stepIndex < steps.length - 1) {
      setDeletingStackIdxs(deletedStackFrames(
        steps[stepIndex]?.memory?.stack,
        steps[stepIndex + 1]?.memory?.stack
      ));
      setDeletingHeapLabels(deletedHeapBlocks(
        steps[stepIndex]?.memory?.heap,
        steps[stepIndex + 1]?.memory?.heap
      ));
      setDeletingData(deletedData(
        steps[stepIndex]?.memory?.data_segment,
        steps[stepIndex + 1]?.memory?.data_segment
      ));
    } else {
      setDeletingStackIdxs(new Set());
      setDeletingHeapLabels(new Set());
      setDeletingData(false);
    }

    setBlinkOn(true);
    blinkRef.current && clearInterval(blinkRef.current);
    blinkRef.current = setInterval(() => setBlinkOn(v => !v), 500);

    return () => {
      blinkRef.current && clearInterval(blinkRef.current);
    };
  }, [stepIndex, steps]);

  // 출력 누적 관리
  useEffect(() => {
    if (!steps.length) return;
    const newLine = steps[stepIndex]?.output || "";
    if (newLine) {
      setAccumulatedOutput(prev => prev + newLine + "\n");
    }
  }, [stepIndex, steps]);

  const handleRun = () => {
    if (!stepsData || stepsData.length === 0) {
      alert('실행 단계 데이터가 없습니다.');
      return;
    }
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

  useEffect(() => {
    return () => {
      intervalRef.current && clearInterval(intervalRef.current);
      blinkRef.current && clearInterval(blinkRef.current);
    };
  }, []);

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

  function CustomStackGraph({ stack }) {
    if (!stack || stack.length === 0) return null;

    return (
      <div className="stack-graph">
        {stack.map((frame, idx) => {
          const filteredVariables = {};
          Object.entries(frame.variables || {}).forEach(([key, value]) => {
            if (
              (typeof value === "string" && /^0x[0-9a-f]+$/i.test(value)) ||
              value === null
            ) return;
            filteredVariables[key] = value;
          });

          const isEmpty = Object.keys(filteredVariables).length === 0;

          let className = "stack-frame";
          if (!isEmpty && blinkStackFrameIdxs.has(idx) && blinkOn) className += " blink";
          if (!isEmpty && deletingStackIdxs.has(idx) && blinkOn) className += " delete-blink";

          if (isEmpty) return null;

          return (
            <div className={className} key={idx}>
              <div className="stack-variable-container">
                {Object.entries(filteredVariables).map(([key, value], i) => (
                  <div className="stack-variable" key={i}>
                    {key} = {String(value)}
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    );
  }

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
          const [addr, val] = Object.entries(block)[0];
          const displayName = addrToVarName[addr] || addr;
          let className = "heap-block";
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

  function CustomDataGraph({ data }) {
    const [displayData, setDisplayData] = useState(data);

    useEffect(() => {
      if (deletingData) {
        const timer = setTimeout(() => {
          setDisplayData(data);
        }, 500);
        return () => clearTimeout(timer);
      } else {
        setDisplayData(data);
      }
    }, [data, deletingData]);

    if (!displayData || Object.keys(displayData).length === 0) return null;

    let className = "data-graph";
    if (blinkDataGraph && blinkOn) className += " blink";
    if (deletingData && blinkOn) className += " delete-blink";

    return (
      <div className={className}>
        {Object.entries(displayData).map(([key, value], i) => (
          <div className="data-variable" key={i}>
            {key} = {value}
          </div>
        ))}
      </div>
    );
  }

  const currentStep = steps[stepIndex] || { memory: { stack: [], heap: [], data_segment: {} }, output: '', line: '', line_index: '' };

  return (
    <div className="container">
      <div className="left-panel">
        <h2>코드입력창</h2>
        <div className="scrollable-container">
          <div className="line-numbers" ref={lineRef}>{generateLineNumbers()}</div>
          <textarea
            className="code-input"
            placeholder="코드를 입력하세요"
            ref={inputRef}
            value={code}
            onChange={(e) => setCode(e.target.value)}
            onScroll={handleScroll}
          />
        </div>
        <button onClick={handleRun}>실행</button>
        <div className="bottom-divider" />
      </div>
      <div className="right-panel">
        <h2>메모리 시각화</h2>
        <div className="memory-container">
          <div className="memory-row">
            <div className="mem-section">
              <div className="mem-title">
                Stack
                <img src="/question_mark.png" alt="스택 정보" className="help-icon" title="스택 정보" />
              </div>
              <div className="mem-box">
                <div className="mem-content stack-area">
                  <CustomStackGraph stack={currentStep.memory.stack} />
                </div>
              </div>
            </div>
            <div className="mem-section">
              <div className="mem-title">
                Heap
                <img src="/question_mark.png" alt="힙 정보" className="help-icon" title="힙 정보" />
              </div>
              <div className="mem-box">
                <div className="mem-content">
                  <CustomHeapGraph heap={currentStep.memory.heap} stack={currentStep.memory.stack} />
                </div>
              </div>
            </div>
            <div className="right-column">
              <div className="mem-section">
                <div className="mem-title">
                  Code
                  <img src="/question_mark.png" alt="코드 정보" className="help-icon" title="코드 및 데이터" />
                </div>
                <div className="mem-box code-box">
                  <div className="mem-content">
                    <CustomDataGraph data={currentStep.memory.data_segment} />
                  </div>
                </div>
              </div>
              <div className="output-area">
                <div className="mem-title">출력 결과</div>
                <div className="output-box">
                  {accumulatedOutput || '출력 결과가 여기에 표시됩니다'}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
