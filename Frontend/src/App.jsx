// 전체적인 UI 지정하는 파일 2025.07.01 ing~
import React, { useState } from "react";
import "./App.css";  // CSS 파일 src 바로 밑에 있음여

function App() {
  const [code, setCode] = useState("");
  const [output, setOutput] = useState("출력 결과가 여기에 표시됩니다");

  const handleRun = () => {
    setOutput("실행 버튼 클릭됨 (FastAPI 연결 예정)");  //나중에 fastapi 연결되면 fetch() 넣을 거임, 지금은 걍 텍스트만 출력됨
  };

  return (
    <div className="container">
      {/* 좌측: 코드 입력창 */}
      <div className="left-panel">
        <h2>코드입력창</h2>
        <textarea
          value={code}
          onChange={(e) => setCode(e.target.value)}
          rows={22}
          placeholder="여기에 코드를 입력하세요"
        />
        <button onClick={handleRun}>실행</button>
      </div>

      {/* 우측: 메모리 시각화 */}
      <div className="right-panel">
        <h2>메모리 시각화</h2>
        <div className="memory-area">
          <div className="mem-box">Stack <span title="스택 영역 설명">❔</span></div>
          <div className="mem-box">Heap <span title="힙 영역 설명">❔</span></div>
          <div className="mem-box">Data <span title="데이터 영역 설명">❔</span></div>
        </div>
        <div className="output-area">
          <h4>출력 결과</h4>
          <div className="output-box">{output}</div>
        </div>
      </div>
    </div>
  );
}

export default App;