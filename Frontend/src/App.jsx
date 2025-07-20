import React, { useRef, useState } from 'react';
import './App.css';
import { parseCodeToSteps } from './utils/parseCodeToSteps';
import StackGraph from './components/StackGraph';
import HeapGraph from './components/HeapGraph';
import DataGraph from './components/DataGraph';

function App() {
  const [code, setCode] = useState('');
  const [steps, setSteps] = useState([]);
  const [stepIndex, setStepIndex] = useState(0);
  const inputRef = useRef(null);
  const lineRef = useRef(null);

  const handleRun = () => {
    const trimmedCode = code.trim();
    if (!trimmedCode) {
      alert('코드를 입력해주세요.');
      return;
    }

    const generatedSteps = parseCodeToSteps(trimmedCode);
    if (!generatedSteps || generatedSteps.length === 0) {
      alert('분석된 실행 단계가 없습니다.');
      return;
    }

    setSteps(generatedSteps);
    setStepIndex(0);

    let current = 0;
    const interval = setInterval(() => {
      current += 1;
      if (current >= generatedSteps.length) {
        clearInterval(interval);
      } else {
        setStepIndex(current);
      }
    }, 1000);
  };

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

  const currentStep = steps[stepIndex] || { stack: [], heap: [], output: '', data: [], code: null };

  return (
    <div className="container">
      {/* 좌측: 코드 입력창 */}
      <div className="left-panel">
        <h2>코드입력창</h2>
        <div className="scrollable-container">
          <div className="line-numbers" ref={lineRef}>
            {generateLineNumbers()}
          </div>
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

      {/* 우측: 메모리 시각화 패널 */}
      <div className="right-panel">
        <h2>메모리 시각화</h2>
        <div className="memory-container">
          <div className="memory-row">

            {/* ✅ Stack 영역 */}
            <div className="mem-section">
              <div className="mem-title">
                Stack
                <img src="/question_mark.png" alt="스택 정보" className="help-icon" title="스택 정보" />
              </div>
              <div className="mem-box">
                <div className="mem-content stack-area">{/* 핵심: 아래→위 쌓임 */}
                  <StackGraph stack={currentStep.stack} />
                </div>
                <img src="/hci_logo.png" alt="HCI Logo" className="hci-logo" />
              </div>
            </div>

            {/* Heap 영역 */}
            <div className="mem-section">
              <div className="mem-title">
                Heap
                <img src="/question_mark.png" alt="힙 정보" className="help-icon" title="힙 정보" />
              </div>
              <div className="mem-box">
                <div className="mem-content">
                  <HeapGraph heap={currentStep.heap} />
                </div>
              </div>
            </div>

            {/* Data(Code) 시각화 영역 */}
            <div className="right-column">
              <div className="mem-section">
                <div className="mem-title">
                  Code
                  <img src="/question_mark.png" alt="코드 정보" className="help-icon" title="코드 및 데이터" />
                </div>
                <div className="mem-box code-box">
                  <div className="mem-content">
                    <DataGraph data={currentStep.data} />
                  </div>
                </div>
              </div>

              {/* 출력 결과 영역 */}
              <div className="output-area">
                <div className="mem-title">출력 결과</div>
                <div className="output-box">
                  {currentStep.output || '출력 결과가 여기에 표시됩니다'}
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
