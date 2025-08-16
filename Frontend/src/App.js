// src/App.js
import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'; //화면 전환을 위한 라우터
import MainMenu from './MainMenu'; //메인메뉴 컴포넌트
import CodeEditor from './App.jsx'; //코드 실행창 컴포넌트
import GuideMode from './GuideMode'; //가이드 모드 컴포넌트

// 현송 : 가이드 모드 주소 추가 및 라우팅, 버튼 연동할거임
function App() {
  return (
    <Router>
      <Routes>
        {/* / 주소로 들어가면 메인메뉴 */}
        <Route path="/" element={<MainMenu />} /> 
        {/* /editior 주소로 들어가면 코드실행창 */}
        <Route path="/editor" element={<CodeEditor />} />
        {/* /GuideMode 주소로 들어가면 가이드모드 (버튼 클릭해서 들어갈 예정)*/}
        <Route path="/GuideMode" element={<GuideMode />} />
      </Routes>
    </Router>
  );
}


export default App;
