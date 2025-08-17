// src/App.js
import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import MainMenu from './MainMenu';   // 메인메뉴 컴포넌트
import CodeEditor from './App.jsx';  // 코드 실행창 컴포넌트 (= App.jsx)
import GuideMode from './GuideMode'; // 가이드 모드 컴포넌트

function App() {
  return (
    <Router>
      <Routes>
        {/* / 주소로 들어가면 메인메뉴 */}
        <Route path="/" element={<MainMenu />} /> 
        {/* /editor 주소로 들어가면 코드 실행창 */}
        <Route path="/editor" element={<CodeEditor />} />
        {/* /GuideMode 주소로 들어가면 가이드모드 */}
        <Route path="/GuideMode" element={<GuideMode />} />
      </Routes>
    </Router>
  );
}

// 라우트에 따라 body class 다르게 주는 부분
function BodyClassController() {
  const location = useLocation();

  useEffect(() => {
    if (location.pathname === "/") {
      document.body.className = "main-menu-body"; // 메인 메뉴 전용 배경
    } else if (location.pathname === "/editor") {
      document.body.className = "editor-body"; // 코드 실행창 전용 배경
    } else if (location.pathname === "/GuideMode") {
      document.body.className = "guide-mode-body"; // 가이드 모드 전용 배경 (추가 옵션)
    } else {
      document.body.className = "";
    }
  }, [location]);

  return null;
}

export default App;
