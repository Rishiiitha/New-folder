// src/Dashboard.jsx
import React from "react";
import "./Dashboard.css";

function Dashboard({ onNavigateToLogin }) {
  return (
    <div className="dashboard-split">
      {/* Left Section */}
      <div className="dashboard-left">
        <div className="logo">🎤 VoiceBot</div>

        {/* Login / Signup box at top right of left section */}
        <div className="auth-box-left">
          <button
            className="login-top-btn"
            onClick={() => onNavigateToLogin("login")}
          >
            Login
          </button>
          <button
            className="signup-top-btn"
            onClick={() => onNavigateToLogin("signup")}
          >
            Signup
          </button>
        </div>

        <div className="left-content">
          <h1 className="main-heading">Empower Your Voice with AI</h1>
          <p className="subtext">
            Transform the way you communicate. Manage, monitor, and enhance
            conversations with an intelligent voice assistant built for the
            future.
          </p>

          <div className="center-start">
            <button
              className="get-started-btn big"
              onClick={() => onNavigateToLogin("user")}
            >
              Get Started →
            </button>
          </div>
        </div>
      </div>

      {/* Right Section (animation untouched) */}
      <div className="dashboard-right">
        <div className="wave-container">
          <div className="wave wave1"></div>
          <div className="wave wave2"></div>
          <div className="wave wave3"></div>
        </div>
      </div>

      {/* Footer */}
      <footer className="footer">
        © 2025 Audio Team | Designed by <b>Kavin (Frontend)</b>
      </footer>
    </div>
  );
}

export default Dashboard;
