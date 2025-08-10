import React, { useRef, useState, useMemo, useEffect } from 'react'; // [확인] useMemo 대소문자 OK
import { useNavigate } from 'react-router-dom';
import './App.css';

function App() {
  const [steps, setSteps] = useState([]); // 실행 단계(여기로 json 파일 받아올 예정)
  const [code, setCode] = useState('');
  const [infoVisible, setInfoVisible] = useState(null); // 'stack' | 'heap' | 'data' | null
  const [error, setError] = useState(''); // 에러 메시지 상태
  const [loading, setLoading] = useState(true); // 로딩 상태
  const [allclickBtn, setAllClickBtn] = useState(false); // 전체실행 버튼 클릭 (네 이름 유지)

  useEffect(() => {
    // 초기 로딩 상태 설정, json 파일 불러오기
    fetch('/data/sample.json') // [CHANGE] public 밑은 절대경로로 접근 (기존: 'Frontend/public/data/sample.json')
      .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then(json => setSteps(Array.isArray(json) ? json : []))
      .catch(err => setError('json 파일 로드 실패: ' + err.message))
      .finally(() => setLoading(false));
  }, []);

  // [ADD] 출력 병합 로직: time/line_index 기준 정렬 → output만 줄바꿈으로 합치기
  const fullOutput = useMemo(() => {
    if (!steps?.length) return '';
    return steps
      .slice()
      .sort(
        (a, b) =>
          (a?.time ?? 0) - (b?.time ?? 0) ||
          (a?.line_index ?? 0) - (b?.line_index ?? 0)
      )
      .map(s => (s?.output ?? '').trim())
      .filter(Boolean)
      .join('\n');
  }, [steps]);

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

  // [ADD] 실행 버튼 핸들러 (나중에 백엔드 붙이면 여기서 API 호출 후 setSteps로 교체)
  const handleRunAll = () => {
    setAllClickBtn(true);
  };

  const handleRunStep = () => {
    // 한 줄 실행은 담당 파트 연동 시 구현
    alert('한 줄 실행은 나중에 연결 예정입니다.');
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
              <button onClick={handleRunStep}>한 줄 실행</button> {/* [ADD] onClick 연결 */}
              <button onClick={handleRunAll} disabled={loading}>전체 실행</button> {/* [ADD] onClick/disabled */}
            </div>
            <button
              className="full-width-btn"
              onClick={() => setAllClickBtn(false)} // [ADD] 출력 표시만 초기화 (시각화는 담당 파트)
            >
              시각화 초기화
            </button>
          </div>
        </div>

        {/* 오른쪽 메모리 구조 시각화 */}
        <div className="right-panel">
          <h2>메모리 시각화</h2>
          <div className="memory-container">
            <div className="memory-row">

              {/* Stack */}
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
                  <div className="mem-content"></div>
                </div>
              </div>

              {/* Heap */}
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
                  <div className="mem-content"></div>
                </div>
              </div>

              {/* Data + 출력 결과 */}
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

                {/* Data 영역 */}
                <div className="mem-box code-box">
                  <div className="mem-content"></div>
                </div>

                {/* 출력 결과 */}
                <div className="output-section pointer-allowed">
                  <div className="mem-title">출력 결과</div>
                  <div className="output-box" style={{ whiteSpace: 'pre-wrap' }}>
                    {/* [CHANGE] 조건부 렌더링: 로딩/에러/안내/출력 */}
                    {loading && '로딩 중...'}
                    {!loading && error && <span style={{ color: '#d33' }}>{error}</span>}
                    {!loading && !error && !allclickBtn && '전체 실행을 눌러주세요'}
                    {!loading && !error && allclickBtn && (fullOutput ? fullOutput : '(출력 없음)')}
                  </div>
                </div>
              </div>
            </div>
            
          </div>
        </div>
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
