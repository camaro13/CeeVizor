import React, { useState } from 'react';
import axios from 'axios';

function CodeEditor() {
  const [code, setCode] = useState('');
  const [input, setInput] = useState('');
  const [output, setOutput] = useState('');
  const [loading, setLoading] = useState(false);


  return (
    <div>
      <h2> C 코드</h2>
      <textarea
        rows={12}
        cols={80}
        value={code}
        onChange={(e) => setCode(e.target.value)}
        placeholder="여기에 C 코드를 입력하세요"
      />
      <h2>입력값</h2>
      <textarea
        rows={3}
        cols={80}
        value={input}
        onChange={(e) => setInput(e.target.value)}
        placeholder="scanf용 입력값을 여기에 (예: 3\n4)"
      />
      <br />
      <button onClick={handleRun} disabled={loading}>
        {loading ? '실행 중...' : '컴파일 & 실행'}
      </button>
      <h2> 실행 결과</h2>
      <pre style={{
        backgroundColor: "#000",
        color: "#0f0",
        padding: "10px",
        fontFamily: "monospace",
        minHeight: "150px"
      }}>{output}</pre>
    </div>
  );
}

export default CodeEditor;