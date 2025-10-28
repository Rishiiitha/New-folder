import React, { useState, useEffect } from 'react';
import './ParentDashboard.css';
import Sidebar from './Sidebar';
import Chatbot from './Chatbot.jsx';
import { FaBars } from 'react-icons/fa';

// (Your handleApiError function)
const handleApiError = (res) => {
  if (res.status === 401 || res.status === 403) {
    alert("Session expired. Please log in again.");
    localStorage.removeItem("access_token");
    window.location.href = '/login';
    return true; 
  }
  return false;
};

// This is the main view (Rewards + Chatbot)
const DashboardView = ({ rewardData, currentSessionId, setCurrentSessionId }) => (
  <>
    <div className="dashboard-section">
      <h2>Student Reward Points</h2>
      {rewardData ? (
        <div className="student-card reward-card">
          <div className="student-header">
            <h3>{rewardData.student_name}</h3> 
            <p className="student-email">Roll No: {rewardData.roll_no}</p>
          </div>
          <div className="student-details">
              <div className="detail-item">
              <strong>Mentor</strong>
              <span>{rewardData.mentor_name}</span>
            </div>
            <div className="detail-item">
              <strong>Cumulative Points</strong>
              <span>{parseFloat(rewardData.cumulative_reward_points).toFixed(2)}</span>
            </div>
            <div className="detail-item">
              <strong>Redeemed Points</strong>
              <span>{parseFloat(rewardData.redeemed_points).toFixed(2)}</span>
            </div>
            <div className="detail-item balance">
              <strong>Balance Points</strong>
              <span>{parseFloat(rewardData.balance_points).toFixed(2)}</span>
            </div>
          </div>
        </div>
      ) : (
        <p className="no-students">
          No reward point data found for this account.
        </p>
      )}
    </div>
    {/* Pass session state to the chatbot */}
    <Chatbot 
      currentSessionId={currentSessionId}
      setCurrentSessionId={setCurrentSessionId}
    />
  </>
);

// --- Main Dashboard Component ---
function ParentDashboard() {
  const [rewardData, setRewardData] = useState(null); 
  const [loading, setLoading] = useState(true);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [activeView, setActiveView] = useState('dashboard');
  
  // --- This is the new, crucial piece of state ---
  // null = "New Chat"
  const [currentSessionId, setCurrentSessionId] = useState(null); 

  // (Your useEffect for fetching rewardData - NO CHANGES NEEDED)
  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      localStorage.removeItem("access_token");
      window.location.href = '/login';
      return;
    }
    const headers = {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    };
    fetch("http://127.0.0.1:8000/auth/reward-points", { 
      method: 'GET', 
      headers 
    })
    .then(async (res) => {
      if (handleApiError(res)) return null;
      if (!res.ok) throw new Error(`Network error: ${res.status}`);
      return res.json();
    })
    .then(data => {
      if (data) setRewardData(data);
      setLoading(false);
    })
    .catch(err => {
      console.error("Error fetching reward data:", err);
      setLoading(false);
    });
  }, []);

  if (loading) {
    return <div className="dashboard-loading">Loading Dashboard Data...</div>;
  }

  // Helper to render the correct main page (e.g., Dashboard, Settings, etc.)
  const renderActiveView = () => {
    switch (activeView) {
      case 'dashboard':
        return <DashboardView 
                  rewardData={rewardData} 
                  currentSessionId={currentSessionId}
                  setCurrentSessionId={setCurrentSessionId}
                />;
      // You no longer need a 'history' case here, it's part of the sidebar
      case 'settings':
        return <h2>Settings (Coming Soon)</h2>;
      case 'help':
        return <h2>Help (Coming Soon)</h2>;
      default:
        return <DashboardView 
                  rewardData={rewardData} 
                  currentSessionId={currentSessionId}
                  setCurrentSessionId={setCurrentSessionId}
                />;
    }
  };

  return (
    <div className="dashboard-container"> 
      <Sidebar 
        isOpen={isSidebarOpen} 
        setIsOpen={setIsSidebarOpen}
        activeView={activeView}
        setActiveView={setActiveView}
        currentSessionId={currentSessionId}
        setCurrentSessionId={setCurrentSessionId}
      />
      
      <div className="dashboard-content"> 
        <header className="dashboard-header">
          <button 
            className="sidebar-toggle-button" 
            onClick={() => setIsSidebarOpen(true)}
          >
            <FaBars />
          </button>
          
          <div className="dashboard-title">
            <h1>👨‍👩‍👧 Parent Dashboard</h1>
            <p className="welcome-text">Welcome back, Parent</p>
          </div>
        </header>

        <main className="dashboard-main">
          {renderActiveView()}
        </main>

        <footer className="dashboard-footer">
          <p>© 2025 EduVoice System | Designed for Parents</p>
        </footer>
      </div>
    </div>
  );
}

export default ParentDashboard;