import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App.js'; // App 전체 UI를 불러오기 -> App.jsx에서 App.js로 변경

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
