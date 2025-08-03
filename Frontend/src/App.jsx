import React, { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import './App.css';

function App() {
  const [code, setCode] = useState('');
  const [infoVisible, setInfoVisible] = useState(null); // 'stack' | 'heap' | 'data' | null
  const inputRef = useRef(null);
  const lineRef = useRef(null);

  const navigate = useNavigate();

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

  const toggleInfo = (type) => {
    setInfoVisible((prev) => (prev === type ? null : type));

  
  };

  return (
    <div className="app-wrapper">
      {/* 상단 전체 컨텐츠 */}
      <div className="container">
        {/* 왼쪽 코드 입력창 */}
        <button onClick={() => navigate('/')} className="back-button">메인화면으로</button> {/* 뒤로가기 버튼*/}
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
              // 들여쓰기 기능 추가
              onKeyDown={(e) => {
                if (e.key === 'Tab') {
                  e.preventDefault();
                  const start = e.target.selectionStart;
                  const end = e.target.selectionEnd;
                  const indent = '    '; // 들여쓰기 (스페이스 4칸)

                  const updatedCode = code.substring(0, start) + indent + code.substring(end);
                  setCode(updatedCode);

                  setTimeout(() => {
                    if (inputRef.current) {
                      inputRef.current.selectionStart =
                        inputRef.current.selectionEnd = start + indent.length;
                    }
                  }, 0);
                }
              }}
            />
          </div>

          {/* 버튼 컨테이너 */}
          <div className="button-container">
            <div className="top-buttons">
              <button>한 줄 실행</button>
              <button>전체 실행</button>
            </div>
            <button className="full-width-btn">시각화 초기화</button>
          </div>
        </div>

        {/* 오른쪽 메모리 구조 시각화 */}
        <div className="right-panel">
          <h2>메모리 시각화</h2>
          <div className="memory-container">
            <div className="memory-row">
              {/* Stack */}
              <div className="mem-section">
                <div className="mem-title">
                  Stack
                  <img
                    src="/question_mark.png"
                    alt="스택 정보"
                    className="help-icon"
                    onClick={() => toggleInfo('stack')}
                  />
                </div>
                <div className="mem-box">
                  <div className="mem-content"></div>
                </div>
              </div>

              {/* Heap */}
              <div className="mem-section">
                <div className="mem-title">
                  Heap
                  <img
                    src="/question_mark.png"
                    alt="힙 정보"
                    className="help-icon"
                    onClick={() => toggleInfo('heap')}
                  />
                </div>
                <div className="mem-box">
                  <div className="mem-content"></div>
                </div>
              </div>

              {/* Data + Output */}
              <div className="right-column">
                <div className="mem-section">
                  <div className="mem-title">
                    Data
                    <img
                      src="/question_mark.png"
                      alt="데이터 정보"
                      className="help-icon"
                      onClick={() => toggleInfo('data')}
                    />
                  </div>
                  <div className="mem-box code-box">
                    <div className="mem-content"></div>
                  </div>
                </div>

                <div className="output-area">
                  <div className="mem-title">출력 결과</div>
                  <div className="output-box">출력 결과가 여기에 표시됩니다</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* 설명창 */}
        {infoVisible && (
          <div className="info-popup">
            <button className="close-btn" onClick={() => setInfoVisible(null)}>×</button>
            {infoVisible === 'stack' && (
              <p><strong>Stack:</strong> 함수 호출 시 자동으로 생성되는 스택프레임들이 저장되는 공간입니다.</p>
            )}
            {infoVisible === 'heap' && (
              <p><strong>Heap:</strong> 동적으로 할당된 배열, 구조체 등의 객체들이 저장되는 메모리 영역입니다.</p>
            )}
            {infoVisible === 'data' && (
              <p><strong>Data:</strong> 전역 변수 및 정적 변수를 할당하는 영역입니다.</p>
            )}
          </div>
        )}
      </div>

      {/* 푸터 */}
      <div className="footer">
        <div className="bottom-divider"></div>
        <img className="hci-logo" src="/hci_logo.png" alt="HCI Logo" />
      </div>
    </div>
  );
}

export default App;
