import React, { useState } from 'react';
import { BrowserRouter as Router, Routes, Route, useNavigate } from 'react-router-dom';
import Dashboard from './Dashboard.jsx';
import Login from './Login.jsx';
import ParentDashboard from './ParentDashboard.jsx';
import AdminDashboard from './AdminDashboard.jsx';
import StudentDashboard from './StudentDashboard.jsx';

function App() {
  const [selectedRole, setSelectedRole] = useState(null);

  function HomeWrapper() {
    const navigate = useNavigate();

    const handleRoleSelect = (role) => {
      setSelectedRole(role);
      navigate('/login'); // Navigate to the login page
    };

    return <Dashboard onNavigateToLogin={handleRoleSelect} />;
  }

  function LoginWrapper() {
    const navigate = useNavigate();

    const handleBack = () => {
      setSelectedRole(null);
      navigate('/'); // Navigate back to the landing page
    };

    return <Login selectedRole={selectedRole} onBack={handleBack} />;
  }

  return (
    <Router>
      <Routes>
        <Route path="/" element={<HomeWrapper />} />
        <Route path="/login" element={<LoginWrapper />} />
        <Route path="/parent-dashboard" element={<ParentDashboard />} />
        <Route path="/admin-dashboard" element={<AdminDashboard />} />
        <Route path="/student-dashboard" element={<StudentDashboard />} />
        <Route path="*" element={<HomeWrapper />} />
      </Routes>
    </Router>
  );
}

export default App;