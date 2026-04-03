import React, { useState, useEffect, useCallback } from "react";
import "./AdminDashboard.css";

const getAuthToken = () => {
  const token = localStorage.getItem("access_token");
  if (!token) {
    handleLogout();
    return null;
  }
  return token;
};

const handleApiError = (res) => {
  if (res.status === 401 || res.status === 403) {
    alert("Your session has expired or you lack permissions. Please log in again.");
    handleLogout();
    return true;
  }
  return false;
};

const handleLogout = () => {
  localStorage.removeItem("access_token");
  window.location.href = "/login";
};

const API_URL = "http://127.0.0.1:8000";

function AdminDashboard() {
  const [selectedFile, setSelectedFile] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [message, setMessage] = useState("");
  const [users, setUsers] = useState([]);
  
  const userCounts = users.reduce(
    (acc, user) => {
      if (user.role === 'student') {
        acc.student = (acc.student || 0) + 1;
      } else {
        acc[user.role] = (acc[user.role] || 0) + 1;
      }
      return acc;
    },
    { admin: 0, parent: 0, student: 0 }
  );

  const fetchDocuments = useCallback(async () => {
    const token = getAuthToken();
    if (!token) return;

    setMessage("Loading documents...");
    try {
      const res = await fetch(`${API_URL}/ingest/list/`, {
        headers: { "Authorization": `Bearer ${token}` },
      });

      if (handleApiError(res)) return;

      if (res.ok) {
        const data = await res.json();
        setDocuments(data.documents || []);
        setMessage("");
      } else {
        setMessage("Error loading documents.");
      }
    } catch (error) {
      setMessage("Network error fetching documents.");
    }
  }, []);

  const fetchUsers = useCallback(async () => {
    const token = getAuthToken();
    if (!token) return;
    
    try {
      const res = await fetch(`${API_URL}/auth/users`, {
        headers: { "Authorization": `Bearer ${token}` },
      });

      if (handleApiError(res)) return;

      if (res.ok) {
        const data = await res.json();
        setUsers(data || []);
      } else {
        console.error("Failed to fetch users");
      }
    } catch (error) {
      console.error("Network error fetching users:", error);
    }
  }, []);

  useEffect(() => {
    fetchDocuments();
    fetchUsers();
  }, [fetchDocuments, fetchUsers]);


  const handleFileChange = (e) => setSelectedFile(e.target.files[0]);

  const handleUpload = async () => {
    const token = getAuthToken();
    if (!token) return;

    if (!selectedFile) {
      setMessage("Please select a file first.");
      return;
    }

    setMessage("Uploading file...");
    
    const formData = new FormData();
    formData.append("file", selectedFile);

    try {
      const res = await fetch(`${API_URL}/ingest/upload/`, {
        method: "POST",
        headers: { "Authorization": `Bearer ${token}` },
        body: formData,
      });

      if (handleApiError(res)) return;
      
      const data = await res.json();
      if (res.ok) {
        setMessage(data.message);
        setSelectedFile(null); // Clear the file input
        document.querySelector('input[type="file"]').value = ""; // Reset input field
        fetchDocuments(); // Refresh the list
      } else {
        setMessage(`Upload Failed: ${data.detail}`);
      }
    } catch (error) {
      setMessage("Network error during upload.");
    }
  };

  const handleSearch = async () => {
    const token = getAuthToken();
    if (!token) return;

    if (!searchQuery.trim()) {
      setSearchResults([]);
      return;
    }
    
    try {
      const res = await fetch(
        `${API_URL}/ingest/search/?query=${encodeURIComponent(searchQuery)}`,
        {
          headers: { "Authorization": `Bearer ${token}` },
        }
      );

      if (handleApiError(res)) return;
      
      if (res.ok) {
        const data = await res.json();
        setSearchResults(data);
      } else {
        setMessage("Search failed.");
      }
    } catch (error) {
      setMessage("Network error during search.");
    }
  };

  const handleDelete = async (filename) => {
    const token = getAuthToken();
    if (!token) return;

    if (!window.confirm(`Are you sure you want to delete ${filename}?`)) return;

    setMessage(`Deleting ${filename}...`);
    try {
      const res = await fetch(`${API_URL}/ingest/delete/${filename}`, {
        method: "DELETE",
        headers: { "Authorization": `Bearer ${token}` },
      });

      if (handleApiError(res)) return;

      const data = await res.json();
      if (res.ok) {
        setMessage(data.message);
        fetchDocuments(); // Refresh the list
      } else {
        setMessage(`Delete Failed: ${data.detail}`);
      }
    } catch (error) {
      setMessage("Network error during delete.");
    }
  };

  const handleDeleteAll = async () => {
    const token = getAuthToken();
    if (!token) return;
    
    if (!window.confirm("DANGER: Are you sure you want to delete ALL documents?")) return;

    setMessage("Deleting all documents...");
    try {
      const res = await fetch(`${API_URL}/ingest/delete_collection/`, {
        method: "DELETE",
        headers: { "Authorization": `Bearer ${token}` },
      });
      
      if (handleApiError(res)) return;
      
      const data = await res.json();
      if (res.ok) {
        setMessage(data.message);
        fetchDocuments(); // Refresh the list
      } else {
        setMessage(`Delete Failed: ${data.detail}`);
      }
    } catch (error) {
      setMessage("Network error during delete all.");
    }
  };

  return (
    <div className="admin-body">
      <header className="admin-header">
        <h1>Admin Dashboard</h1>
        <button className="logout-button" onClick={handleLogout}>
          Logout
        </button>
      </header>

      <section className="summary-section">
        <div className="summary-card admin">
          <h3>Admins</h3>
          <p>{userCounts.admin}</p>
        </div>
        <div className="summary-card parent">
          <h3>Parents</h3>
          <p>{userCounts.parent}</p>
        </div>
        <div className="summary-card user">
          <h3>Students</h3>
          <p>{userCounts.student}</p>
        </div>
      </section>

      <main className="admin-main">
        {message && <div className="admin-message">{message}</div>}

        <div className="admin-grid">
          <div className="doc-management">
            <h2>📄 Document Management</h2>

            <div className="admin-card">
              <h3>1. Upload New Document</h3>
              <input type="file" accept=".pdf" onChange={handleFileChange} />
              <button onClick={handleUpload} disabled={!selectedFile}>
                Upload File
              </button>
            </div>

            <div className="admin-card">
              <h3>2. Search Documents</h3>
              <input
                type="text"
                placeholder="Search document content..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
              <button onClick={handleSearch}>Search</button>
              <div className="search-results">
                {searchResults.map((result, index) => (
                  <div key={index} className="result-item">
                    <strong>{result.source}</strong>
                    <p>{result.preview}...</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="admin-card">
              <h3>3. Uploaded Documents</h3>
              <ul className="doc-list">
                {documents.length > 0 ? (
                  documents.map((doc, index) => (
                    <li key={index}>
                      <span>{doc}</span>
                      <button className="delete-btn" onClick={() => handleDelete(doc)}>
                        Delete
                      </button>
                    </li>
                  ))
                ) : (
                  <li>No documents found.</li>
                )}
              </ul>
            </div>

            <div className="admin-card danger-zone">
              <h3>Danger Zone</h3>
              <button className="delete-all-btn" onClick={handleDeleteAll}>
                Delete All Documents
              </button>
            </div>
          </div>

          <div className="user-status">
            <h2>👥 User Status</h2>
            <div className="admin-card">
              <h3>Active Users</h3>
              <table className="user-table">
                <thead>
                  <tr>
                    <th>Email</th>
                    <th>Role</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((user) => (
                    <tr key={user.id}>
                      <td>{user.email}</td>
                      <td>{user.role}</td>
                      <td>
                        <span className={`status-dot ${user.status.toLowerCase()}`}></span>
                        {user.status}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

export default AdminDashboard;