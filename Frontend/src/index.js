import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App.jsx'; // App 전체 UI를 불러오기

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <App /> 
  </React.StrictMode>
);
