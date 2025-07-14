import React, { useState } from 'react';
import axios from 'axios';

function CodeEditor() {
  const [code, setCode] = useState('');
  const [output, setOutput] = useState('');
  const [loading, setLoading] = useState(false);

  const handleRun = async () => {
    setLoading(true);
    setOutput('');

    const formData = new FormData();
    formData.append('code', code); // 📌 텍스트 필드 'code'로 전송

    try {
      const response = await axios.post('http://localhost:8000/compile', formData);
<<<<<<< Updated upstream
      setOutput(response.data.output || '출력이 없습니다');
=======
      const { output, analysis, timeline } = response.data;
      setOutput(response.data.output || '출력 없음');
>>>>>>> Stashed changes
    } catch (error) {
      const err = error.response?.data?.error || '실행 실패';
      setOutput(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <textarea
        rows={15}
        cols={80}
        value={code}
        onChange={(e) => setCode(e.target.value)}
        placeholder="여기에 C 코드를 입력하세요"
      />
      <br />
      <button onClick={handleRun} disabled={loading}>
        {loading ? '실행 중...' : '컴파일 & 실행'}
      </button>
      <h3>실행 결과:</h3>
      <pre style={{ backgroundColor: '#f4f4f4', padding: '10px' }}>{output}</pre>
    </div>
  );
}

export default CodeEditor;
