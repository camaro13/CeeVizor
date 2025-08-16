// src/GuideMode.jsx
import React from 'react';
import { useNavigate } from 'react-router-dom';
import './GuideMode.css';

const GuideMode = () => {
  const navigate = useNavigate();

  return (
    <div className="guide-container">
      <h1>가이드 모드</h1>
      <p>가이드모드</p>

      <button onClick={() => navigate("/")}>메인메뉴로 돌아가기</button>
    </div>
  );
};

// 
export default GuideMode;
