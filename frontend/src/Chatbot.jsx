import React, { useState, useEffect, useRef } from 'react';
import './Chatbot.css';
const getAuthToken = () => {
  const token = localStorage.getItem("access_token");
  if (!token) {
    window.location.href = '/login';
    return null;
  }
  return token;
};
const handleLogout = () => {
  localStorage.removeItem("access_token");
  window.location.href = '/login';
};
const handleApiError = (res) => {
  if (res.status === 401 || res.status === 403) {
    alert("Session expired. Please log in again.");
    handleLogout();
    return true;
  }
  return false;
};
const speak = (text) => {
  const cleanText = text.replace(/\*/g, '');
  const utterance = new SpeechSynthesisUtterance(cleanText);
  window.speechSynthesis.speak(utterance);
};
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition;
if (SpeechRecognition) {
  recognition = new SpeechRecognition();
  recognition.continuous = false;
  recognition.interimResults = false;
}

// --- Main Chatbot Component ---
function Chatbot({ currentSessionId, setCurrentSessionId }) {
  const [messages, setMessages] = useState([
    { sender: 'bot', text: 'Hi! How can I help you today?' }
  ]);
  const [question, setQuestion] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isListening, setIsListening] = useState(false);
  
  const [abortController, setAbortController] = useState(null);
  
  const chatWindowRef = useRef(null);

  useEffect(() => {
    if (chatWindowRef.current) {
      chatWindowRef.current.scrollTop = chatWindowRef.current.scrollHeight;
    }
  }, [messages]);

  useEffect(() => {
    const fetchHistory = async (sessionId) => {
      const token = getAuthToken();
      if (!token) return;

      setIsLoading(true);
      try {
        const res = await fetch(`http://127.0.0.1:8000/auth/chat/history/${sessionId}`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (handleApiError(res)) return;
        if (!res.ok) throw new Error("Failed to fetch history");

        const data = await res.json();
        const formattedHistory = data.history.map(msg => ({
          sender: msg.type === 'human' ? 'user' : 'bot',
          text: msg.data.content
        }));
        setMessages(formattedHistory);

      } catch (err) {
        console.error("Failed to fetch chat history:", err);
      } finally {
        setIsLoading(false);
      }
    };

    if (currentSessionId) {
      fetchHistory(currentSessionId);
    } else {
      setMessages([{ sender: 'bot', text: 'Hi! How can I help you today?' }]);
    }
  }, [currentSessionId]);

  const sendQuery = async (queryText) => {
    if (!queryText.trim()) return;

    setIsLoading(true);
    setQuestion("");
    setMessages(prev => [...prev, { sender: 'user', text: queryText }]);

    const controller = new AbortController();
    setAbortController(controller);

    const token = getAuthToken();
    if (!token) {
      setIsLoading(false);
      return;
    }

    try {
      const res = await fetch("http://127.0.0.1:8000/bot/ask", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`
        },
        body: JSON.stringify({ 
          question: queryText, 
          session_id: currentSessionId 
        }),
        signal: controller.signal
      });

      let botResponse = "";
      if (res.ok) {
        const data = await res.json();
        botResponse = data.answer;
        if (data.new_session_id) {
          setCurrentSessionId(data.new_session_id);
        }
      } else if (res.status === 401) {
      } else {
      }
      
      setMessages(prev => [...prev, { sender: 'bot', text: botResponse }]);
      speak(botResponse);

    } catch (error) {
      if (error.name === 'AbortError') {
        console.log("Fetch aborted by user.");
        setMessages(prev => [...prev, { sender: 'bot', text: "[Response stopped]" }]);
      } else {
        console.error("Failed to fetch:", error);
        const errorMsg = "Sorry, I couldn't connect to the bot.";
        setMessages(prev => [...prev, { sender: 'bot', text: errorMsg }]);
        speak(errorMsg);
      }
    }
    
    setIsLoading(false);
    setAbortController(null);
  };

  const handleStopClick = () => {
    if (abortController) {
      abortController.abort();
      setAbortController(null);
    }
  };

  const handleFormSubmit = (e) => {
    e.preventDefault();
    sendQuery(question);
  };
  const handleListenClick = () => {
    if (!recognition || isListening) return;
    recognition.onstart = () => setIsListening(true);
    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      setQuestion(transcript);
      sendQuery(transcript);
    };
    recognition.onerror = (event) => {
      console.error("Speech recognition error", event.error);
      setIsListening(false);
    };
    recognition.onend = () => setIsListening(false);
    recognition.start();
  };

  return (
    <div className="chatbot-container">
      <h3>🎤 Smart Voice Assistant</h3>
      <div className="chat-window" ref={chatWindowRef}>
        {messages.map((msg, index) => (
          <div key={index} className={`chat-message ${msg.sender}`}>
            <p>{msg.text}</p>
          </div>
        ))}
        {isLoading && (
          <div className="chat-message bot loading">
            <div className="typing-indicator">
              <span></span><span></span><span></span>
            </div>
          </div>
        )}
      </div>
      
      <form onSubmit={handleFormSubmit} className="chat-form">
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Type or click the mic to talk..."
          disabled={isLoading}
        />

        {isLoading ? (
          <button 
            type="button" 
            className="stop-button" 
            onClick={handleStopClick}
          >
            ■
          </button>
        ) : (
          <button 
            type="button" 
            className={`mic-button ${isListening ? 'listening' : ''}`}
            onClick={handleListenClick}
            disabled={!recognition}
          >
            {isListening ? '...' : '🎙️'}
          </button>
        )}

        <button type="submit" className="send-button" disabled={isLoading}>
          ➤
        </button>
      </form>
    </div>
  );
}

export default Chatbot;