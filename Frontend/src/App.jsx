import React, { useRef, useState } from 'react';
import './App.css';
import axios from 'axios';
import CodeEditor from './CodeEditor';

function App() {
  const [code, setCode] = useState('');
  const [input, setInput] = useState('');
  const [output, setOutput] = useState('');
  const [loading, setLoading] = useState(false);
  const inputRef = useRef(null);
  const lineRef = useRef(null);

  const handleRun = async () => {
    setLoading(true);
    setOutput('');

    const formData = new FormData();
    formData.append('code', code);
    formData.append('input', input);  // 사용자 입력 추가

    try {
      const response = await axios.post('http://localhost:8000/compile', formData);
      const { output, analysis, timeline } = response.data;
      setOutput(response.data.output || '출력 없음');
    } catch (error) {
      const err = error.response?.data?.error || '실행 실패';
      setOutput(err);
    } finally {
      setLoading(false);
    }
  };
  
  const handleScroll = () => {
    if (inputRef.current && lineRef.current) {
      lineRef.current.scrollTop = inputRef.current.scrollTop;
    }
  };

  const generateLineNumbers = () => {
    const lineCount = Math.max(code.split('\n').length, 200);
    return Array.from({ length: lineCount }, (_, i) => (
      <div className="line-number" key={i}>{String(i + 1).padStart(2, '0')}</div>
    ));
  };

  return (
    <div className="container">
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
        <button onClick={handleRun} disabled={loading}>
        {loading ? '실행 중...' : '컴파일 & 실행'}
        </button>
        {/* <button>실행</button> */}
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
                <div className="mem-content"></div>
                <img src="/hci_logo.png" alt="HCI Logo" className="hci-logo" />
              </div>
            </div>

            <div className="mem-section">
              <div className="mem-title">
                Heap
                <img src="/question_mark.png" alt="힙 정보" className="help-icon" title="힙 정보" />
              </div>
              <div className="mem-box">
                <div className="mem-content"></div>
              </div>
            </div>

            <div className="right-column">
              <div className="mem-section">
                <div className="mem-title">
                  Code
                  <img src="/question_mark.png" alt="코드 정보" className="help-icon" title="코드 정보" />
                </div>
                <div className="mem-box code-box">
                  <div className="mem-content"></div>
                </div>
              </div>

              <div className="output-area">
                <div className="mem-title">출력 결과</div>
                <div className="output-box">{output ? <pre>{output}</pre> : '출력 결과가 여기에 표시됩니다'}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;