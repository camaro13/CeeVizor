import React, { useRef, useState } from 'react';
import './App.css';
import StackGraph from './components/StackGraph';
import HeapGraph from './components/HeapGraph';
import DataGraph from './components/DataGraph';

function App() {
  const [code, setCode] = useState('');
  const [steps, setSteps] = useState([]);
  const [stepIndex, setStepIndex] = useState(0);

  const inputRef = useRef(null);
  const lineRef = useRef(null);

  // 🚩 백엔드와 연동하는 부분만 수정!
  const handleRun = async () => {
    const trimmedCode = code.trim();
    if (!trimmedCode) {
      alert('코드를 입력해주세요.');
      return;
    }

    try {
      // 실제 API 엔드포인트 주소와 포트는 상황에 맞게 수정!
      const res = await fetch('http://localhost:3000/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: trimmedCode })
      });

      if (!res.ok) throw new Error('서버 오류!');
      const data = await res.json();

      // 샘플 백엔드 응답: { "received_code": "...코드..." }
      // 실제 응답이 추후 { steps:[{stack, heap, ...}] } 형태라면 아래 예시처럼 매핑 필요

      // 임시 사용: 백엔드가 샘플 응답만 줄 경우
      setSteps([
        {
          stack: [],
          heap: [],
          data: [{ key: 'received_code', value: data.received_code }],
          output: '',
          code: null,
        }
      ]);
      setStepIndex(0);

      // 실제 steps가 넘오면 아래와 같이 처리!
      // setSteps(data.steps); setStepIndex(0);
      // (애니메이션 반복문 등은 필요시 아래 참고 예시처럼 추가)

    } catch (e) {
      alert('서버 오류! 다시 시도해주세요.');
    }
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

  // 현재 스텝 정보 (steps가 비어 있을 시 기본 값)
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

            {/* Stack 영역 */}
            <div className="mem-section">
              <div className="mem-title">
                Stack
                <img src="/question_mark.png" alt="스택 정보" className="help-icon" title="스택 정보" />
              </div>
              <div className="mem-box">
                <div className="mem-content stack-area">
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

            {/* Code + Data & 출력영역 */}
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
