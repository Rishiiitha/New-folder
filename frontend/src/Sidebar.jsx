import React from 'react';
import './Sidebar.css';
import { 
  FaCog, FaQuestionCircle, FaSignOutAlt, FaTachometerAlt, FaTimes,
  FaHistory // <-- 1. Import History Icon
} from 'react-icons/fa';

const handleLogout = () => {
  localStorage.removeItem("access_token");
  window.location.href = '/login';
};

// 2. Accept props: isOpen, setIsOpen, activeView, setActiveView
function Sidebar({ isOpen, setIsOpen, activeView, setActiveView }) {
  
  // 3. Helper function to handle clicks
  const handleItemClick = (viewName) => {
    setActiveView(viewName);
    setIsOpen(false); // Close sidebar on click
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
        {/* 4. Make items clickable and check for 'active' class */}
        <li 
          className={`sidebar-item ${activeView === 'dashboard' ? 'active' : ''}`}
          onClick={() => handleItemClick('dashboard')}
        >
          <FaTachometerAlt />
          <span>Dashboard</span>
        </li>

        {/* This is your new History button */}
        <li 
          className={`sidebar-item ${activeView === 'history' ? 'active' : ''}`}
          onClick={() => handleItemClick('history')}
        >
          <FaHistory />
          <span>Chat History</span>
        </li>
        
        <li 
          className={`sidebar-item ${activeView === 'settings' ? 'active' : ''}`}
          onClick={() => handleItemClick('settings')}
        >
          <FaCog />
          <span>Settings</span>
        </li>
        
        <li 
          className={`sidebar-item ${activeView === 'help' ? 'active' : ''}`}
          onClick={() => handleItemClick('help')}
        >
          <FaQuestionCircle />
          <span>Help</span>
        </li>
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