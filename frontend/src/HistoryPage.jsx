import React, { useState, useEffect } from 'react';
import './HistoryPage.css';

// --- Helper Functions (You can copy from another file) ---
const getAuthToken = () => localStorage.getItem("access_token");

const handleApiError = (res) => {
  if (res.status === 401 || res.status === 403) {
    alert("Session expired. Please log in again.");
    localStorage.removeItem("access_token");
    window.location.href = '/login';
    return true;
  }
  return false;
};

function HistoryPage() {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchHistory = async () => {
      const token = getAuthToken();
      if (!token) {
        setError("You are not logged in.");
        setLoading(false);
        return;
      }

      try {
        const res = await fetch("http://127.0.0.1:8000/auth/chat/history", {
          method: 'GET',
          headers: { 'Authorization': `Bearer ${token}` }
        });

        if (handleApiError(res)) return;
        if (!res.ok) throw new Error(`Server error: ${res.status}`);

        const data = await res.json();
        
        // Data is { history: [{ type: "human", data: { content: "..." } }, ...] }
        setHistory(data.history);
      } catch (err) {
        console.error("Failed to fetch chat history:", err);
        setError("Could not load chat history. Please try again later.");
      } finally {
        setLoading(false);
      }
    };

    fetchHistory();
  }, []);

  if (loading) {
    return <div className="history-loading">Loading Chat History...</div>;
  }

  if (error) {
    return <div className="history-error">{error}</div>;
  }

  return (
    <div className="history-container">
      <h2>Chat History</h2>
      <div className="history-log">
        {history.length > 0 ? (
          history.map((msg, index) => (
            <div key={index} className={`history-message ${msg.type}`}>
              <span className="message-sender">{msg.type === 'human' ? 'You' : 'Bot'}</span>
              <p className="message-content">{msg.data.content}</p>
            </div>
          ))
        ) : (
          <p>No chat history found.</p>
        )}
      </div>
    </div>
  );
}

export default HistoryPage;