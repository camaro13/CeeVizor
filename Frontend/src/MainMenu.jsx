import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import './MainMenu.css';

const MainMenu = () => {
  const navigate = useNavigate();
  const [showMemoryInfo, setShowMemoryInfo] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showUsageInfo, setShowUsageInfo] = useState(false);
  const [showTeamInfo, setShowTeamInfo] = useState(false);

  return (
    <div className="app-wrapper">
      <div className="main-menu-container">
        <div className="center-content">
        <ul className="button-group">
          <li>
            <button className="menu-btn" onClick={() => navigate('/editor')}>
              <div className="btn-content">
                <img src="/icons/code-icon.png" alt="code" />
                <span>코드 실행창</span>
              </div>
            </button>
          </li>
          <li>
            <button className="menu-btn" onClick={() => setShowMemoryInfo(true)}>
              <div className="btn-content">
                <img src="/icons/memo-icon.png" alt="memory" />
                <span>메모리 구조</span>
              </div>
            </button>
          </li>
          <li>
            <button className="menu-btn" onClick={() => setShowSettings(true)}>
              <div className="btn-content">
                <img src="/icons/settings-icon.png" alt="settings" />
                <span>설정</span>
              </div>
            </button>
          </li>
          <li>
            <button className="menu-btn" onClick={() => window.close()}>
              <div className="btn-content">
                <img src="/icons/turnoff-icon.png" alt="exit" />
                <span>종료</span>
              </div>
            </button>
          </li>
        </ul>

        {showMemoryInfo && (
          <div className="modal-overlay">
            <div className="modal left-align">
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
              <button className="sub-btn"
                onClick={() => { setShowSettings(false); navigate('/editor'); }}>
                일반 모드
                </button>
                <button className="sub-btn"
                onClick={() => { setShowSettings(false); navigate('/GuideMode'); }}>
                가이드 모드
                </button>
              <button className="sub-btn" onClick={() => {
                setShowUsageInfo(true);
                setShowSettings(false);
              }}>프로그램 사용법</button>
              <button className="sub-btn" onClick={() => {
                setShowTeamInfo(true);
                setShowSettings(false);
              }}>팀 소개</button>
              <button onClick={() => setShowSettings(false)}>닫기</button>
            </div>
          </div>
        )}

        {/* 프로그램 사용법 모달 */}
        {showUsageInfo && (
          <div className="modal-overlay">
            <div className="modal left-align">
              <h2>프로그램 사용법</h2>
              <ul>
                <li><b>코드 실행창</b> : 코드 입력창에 C언어 코드를 입력하고 실행 결과를 시각화합니다.</li>
                <li><b>한 줄 실행</b> : 한 줄씩 코드를 확인할 수 있습니다.</li>
                <li><b>전체 실행</b>: 코드가 한번에 실행됩니다.</li>
                <li><b>시각화 초기화</b> : 오른쪽 메모리 구조 영역의 메모리 박스가 초기화됩니다.</li>
                <li><b>일반 모드</b> : 코드를 직접 실행시켜서 메모리구조를 확인할 수 있는 모드입니다.</li>
                <li><b>가이드 모드</b> : 전체적인 코드와 메모리구조가 어떤식으로 이어지는지 간단하게 확인할 수 있는 모드입니다.</li>
              </ul>
              <button onClick={() => setShowUsageInfo(false)}>닫기</button>
            </div>
          </div>
        )}

        {/* 팀 소개 모달 */}
        {showTeamInfo && (
          <div className="modal-overlay">
            <div className="modal left-align">
              <h2>팀 소개</h2>
              <p><b>CeeVizor 팀 (오픈소스 개발자대회 2025)</b></p>
              <ul>
                <li><b>최강우</b>: 백엔드 (FastAPI)</li>
                <li><b>김병모</b>: API 연동</li>
                <li><b>허준혁</b>: 메모리 시각화 (D3.js)</li>
                <li><b>김현송</b>: UI/프론트엔드 (React)</li>
              </ul>
              <p>메모리 구조를 쉽게 이해할 수 있도록 시각화한 교육용 프로그램입니다.</p>
              <button onClick={() => setShowTeamInfo(false)}>닫기</button>
            </div>
          </div>
        )}
      </div>

      <div className="footer">
        <div className="bottom-divider"></div>
        <img src="/hci_logo.png" alt="hci logo" className="hci-logo-main" />
      </div>
    </div>
  );
};

export default MainMenu;
