// src/App.js
import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'; //화면 전환을 위한 라우터
import MainMenu from './MainMenu'; //메인메뉴 컴포넌트
import CodeEditor from './App.jsx'; //코드 실행창 컴포넌트

function App() {
  return (
    <Router>
      <Routes>
        {/* / 주소로 들어가면 메인메뉴 */}
        <Route path="/" element={<MainMenu />} /> 
        {/* /editior 주소로 들어가면 코드실행창 */}
        <Route path="/editor" element={<CodeEditor />} />
      </Routes>
    </Router>
  );
}


export default App;
