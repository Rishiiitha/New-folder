import React, { useState, useEffect } from 'react';
import './Sidebar.css';
import { 
  FaCog, FaQuestionCircle, FaSignOutAlt, FaTachometerAlt, FaTimes,
  FaHistory, FaPlus // Import icons for History and New
} from 'react-icons/fa';

// --- Helper Functions ---
const handleLogout = () => {
  localStorage.removeItem("access_token");
  window.location.href = '/login';
};

const getAuthToken = () => localStorage.getItem("access_token");

// --- Main Sidebar Component ---
function Sidebar({ 
  isOpen, setIsOpen, 
  activeView, setActiveView,
  currentSessionId, setCurrentSessionId 
}) {
  
  const [sessions, setSessions] = useState([]); // State for session list

  // --- Fetch Session List ---
  useEffect(() => {
    const token = getAuthToken();
    if (!token || !isOpen) return; // Only fetch if sidebar is open

    fetch("http://127.0.0.1:8000/auth/chat/sessions", {
      headers: { 'Authorization': `Bearer ${token}` }
    })
    .then(res => res.json())
    .then(data => {
      if (data.sessions) {
        setSessions(data.sessions);
      }
    })
    .catch(err => console.error("Failed to fetch sessions:", err));
    
  // Re-fetch sessions if the sidebar is opened OR if a new chat is created
  }, [isOpen, currentSessionId]); 

  
  const handleViewClick = (viewName) => {
    setActiveView(viewName);
    // Don't close sidebar here, let user see the sessions
  };
  
  const handleSessionClick = (sessionId) => {
    setCurrentSessionId(sessionId); // This tells the dashboard to update the chatbot
    setIsOpen(false); // Close sidebar
  };

  return (
    <nav className={`sidebar ${isOpen ? 'open' : ''}`}> 
      <div className="sidebar-header">
        <h3>EduVoice</h3>
        <button className="sidebar-close-button" onClick={() => setIsOpen(false)}>
          <FaTimes />
        </button>
      </div>

      <ul className="sidebar-menu">
        {/* --- Main Navigation --- */}
        <li 
          className={`sidebar-item ${activeView === 'dashboard' ? 'active' : ''}`}
          onClick={() => handleViewClick('dashboard')}
        >
          <FaTachometerAlt />
          <span>Dashboard</span>
        </li>
        <li 
          className={`sidebar-item ${activeView === 'settings' ? 'active' : ''}`}
          onClick={() => handleViewClick('settings')}
        >
          <FaCog />
          <span>Settings</span>
        </li>
        <li 
          className={`sidebar-item ${activeView === 'help' ? 'active' : ''}`}
          onClick={() => handleViewClick('help')}
        >
          <FaQuestionCircle />
          <span>Help</span>
        </li>
        
        {/* --- Session History Section --- */}
        <li className="sidebar-divider">
          <span>Chat History</span>
        </li>
        
        {/* "New Chat" Button */}
        <li 
          className={`sidebar-item session-item ${currentSessionId === null ? 'active-session' : ''}`}
          onClick={() => handleSessionClick(null)}
        >
          <FaPlus />
          <span>New Chat</span>
        </li>
        
        {/* List of past sessions */}
        {sessions.map(session => (
          <li 
            key={session.session_id}
            className={`sidebar-item session-item ${currentSessionId === session.session_id ? 'active-session' : ''}`}
            onClick={() => handleSessionClick(session.session_id)}
          >
            <FaHistory />
            <span className="session-title">{session.title}</span>
          </li>
        ))}
      </ul>

      <div className="sidebar-footer">
        <button className="sidebar-logout-button" onClick={handleLogout}>
          <FaSignOutAlt />
          <span>Logout</span>
        </button>
      </div>
    </nav>
  );
}

export default Sidebar;