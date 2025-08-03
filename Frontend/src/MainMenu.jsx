import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import './MainMenu.css';

const MainMenu = () => {
  const navigate = useNavigate();
  const [showMemoryInfo, setShowMemoryInfo] = useState(false);
  const [showSettings, setShowSettings] = useState(false);

  return (
    <div className="main-menu-container">
      <div className="circle top-left-circle" />
      <div className="circle bottom-right-circle" />

      <div className="center-content">
        <h1 className="main-title">Ceevizoer</h1>
        <p className="sub-title">메모리 구조</p>
      </div>

      <ul className="button-group">
        <li><button className="menu-btn" onClick={() => navigate('/editor')}>코드실행창</button></li>
        <li><button className="menu-btn" onClick={() => setShowMemoryInfo(true)}>메모리 구조</button></li>
        <li><button className="menu-btn" onClick={() => setShowSettings(true)}>설정</button></li>
        <li><button className="menu-btn" onClick={() => window.close()}>종료</button></li>
      </ul>

      {/* 메모리 구조 설명 모달 */}
      {showMemoryInfo && (
        <div className="modal-overlay">
          <div className="modal">
            <h2>메모리 구조란?</h2>
<p>
  프로그램이 실행될 때, 사용하는 메모리는 크게 네 가지로 나뉩니다.
</p>
<ul>
  <li><b>코드 영역</b>: 함수 등의 실행 명령이 저장됩니다.</li>
  <li><b>데이터 영역</b>: 전역 변수, static 변수 등 프로그램 시작부터 끝까지 유지되는 데이터가 저장됩니다.</li>
  <li><b>스택 영역</b>: 함수 호출 시 생성되는 지역 변수들이 저장됩니다. 함수가 끝나면 자동으로 사라집니다.</li>
  <li><b>힙 영역</b>: <code>malloc</code>이나 <code>new</code>로 직접 할당한 메모리가 저장됩니다. <code>free</code>로 직접 해제해야 합니다.</li>
</ul>
<p>
  각 영역은 역할이 다르고, 언제 생기고 사라지는지도 다릅니다. <br />
  메모리 구조를 알면, 프로그램이 어떻게 돌아가는지 더 쉽게 이해할 수 있어요!
</p>
            <button onClick={() => setShowMemoryInfo(false)}>닫기</button>
          </div>
        </div>
      )}

      {/* 설정 모달 */}
      {showSettings && (
        <div className="modal-overlay">
          <div className="modal">
            <h2>설정</h2>
            <button className="sub-btn">일반모드</button>
            <button className="sub-btn">가이드 모드</button>
            <button className="sub-btn">프로그램 사용법</button>
            <button className="sub-btn">팀 소개</button>

            <button onClick={() => setShowSettings(false)}>닫기</button>
          </div>
        </div>
      )}
    </div>
  );
};

export default MainMenu;
