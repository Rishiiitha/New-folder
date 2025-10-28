import React from 'react';
import './ParentDashboard.css'; // Reuse styles
import Chatbot from './Chatbot.jsx'; // 1. Import the new component

// --- Helper function for logout ---
const handleLogout = () => {
  localStorage.removeItem("access_token");
  window.location.href = '/login';
};

function StudentDashboard() {
  return (
    <div className="dashboard-body">
      <header className="dashboard-header">
        <div className="dashboard-title">
          <h1>🎓 Student Dashboard</h1>
          <p className="welcome-text">Welcome back, Student</p>
        </div>
        <button className="logout-button" onClick={handleLogout}>
          Logout
        </button>
      </header>

      <main className="dashboard-main">
        {/* 2. Render the new Chatbot component */}
        <Chatbot />
      </main>

      <footer className="dashboard-footer">
        <p>© 2025 EduVoice System | Designed for Students</p>
      </footer>
    </div>
  );
}

export default StudentDashboard;