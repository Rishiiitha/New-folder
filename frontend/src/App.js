import React, { useState } from 'react';
import {
  BrowserRouter as Router,
  Routes,
  Route,
  useNavigate
} from 'react-router-dom';

// --- 1. IMPORT ALL YOUR PAGE COMPONENTS ---
import Dashboard from './Dashboard.jsx'; // Your landing page
import Login from './Login.jsx';
import ParentDashboard from './ParentDashboard.jsx';
import AdminDashboard from './AdminDashboard.jsx';
import StudentDashboard from './StudentDashboard.jsx'; // The student chat page

function App() {
  const [selectedRole, setSelectedRole] = useState(null);

  // --- 2. WRAPPER COMPONENTS ---
  // These are necessary to use the 'useNavigate' hook

  /**
   * Renders the landing page (Dashboard.jsx)
   * Passes the navigation function to it.
   */
  function HomeWrapper() {
    const navigate = useNavigate();

    const handleRoleSelect = (role) => {
      setSelectedRole(role);
      navigate('/login'); // Navigate to the login page
    };

    // Your Dashboard.jsx expects 'onNavigateToLogin'
    return <Dashboard onNavigateToLogin={handleRoleSelect} />;
  }

  /**
   * Renders the Login page (Login.jsx)
   * Passes the 'selectedRole' and 'onBack' props to it.
   */
  function LoginWrapper() {
    const navigate = useNavigate();

    const handleBack = () => {
      setSelectedRole(null);
      navigate('/'); // Navigate back to the landing page
    };

    // Your Login.jsx expects 'selectedRole' and 'onBack'
    return <Login selectedRole={selectedRole} onBack={handleBack} />;
  }

  // --- 3. ROUTER SETUP ---
  return (
    <Router>
      <Routes>
        {/* Path "/": The main landing page */}
        <Route path="/" element={<HomeWrapper />} />

        {/* Path "/login": The login page */}
        <Route path="/login" element={<LoginWrapper />} />

        {/* --- Dashboard Routes --- */}
        {/* Your Login.jsx redirects to these paths after success */}
        
        <Route path="/parent-dashboard" element={<ParentDashboard />} />
        
        <Route path="/admin-dashboard" element={<AdminDashboard />} />
        
        {/* This is the route for 'student' (which Login.jsx calls '/dashboard') */}
        <Route path="/dashboard" element={<StudentDashboard />} />

        {/* Fallback route: any unknown URL goes back to the home page */}
        <Route path="*" element={<HomeWrapper />} />
      </Routes>
    </Router>
  );
}

export default App;