import React, { useState, useEffect, useRef } from 'react';
import './Chatbot.css'; // We will create this file next

// --- Helper Functions (Defined once at the top) ---

const getAuthToken = () => {
  const token = localStorage.getItem("access_token");
  if (!token) {
    window.location.href = '/login'; // Force logout
    return null;
  }
  return token;
};

const handleLogout = () => {
  localStorage.removeItem("access_token");
  window.location.href = '/login';
};

// --- Helper: Speak Text ---
const speak = (text) => {
  // Cleans up bot text for better speech (removes *, etc.)
  const cleanText = text.replace(/\*/g, '');
  const utterance = new SpeechSynthesisUtterance(cleanText);
  window.speechSynthesis.speak(utterance);
};

// --- Speech Recognition Setup ---
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition;
if (SpeechRecognition) {
  recognition = new SpeechRecognition();
  recognition.continuous = false; // Stop listening after one phrase
  recognition.interimResults = false;
}

function Chatbot() {
  const [messages, setMessages] = useState([
    { sender: 'bot', text: 'Hi! How can I help you today?' }
  ]);
  const [question, setQuestion] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isListening, setIsListening] = useState(false);
  
  // Ref for the chat window to auto-scroll
  const chatWindowRef = useRef(null);

  // --- Auto-scroll to bottom ---
  useEffect(() => {
    if (chatWindowRef.current) {
      chatWindowRef.current.scrollTop = chatWindowRef.current.scrollHeight;
    }
  }, [messages]);

  // --- Core API Call Function ---
  const sendQuery = async (queryText) => {
    if (!queryText.trim()) return;

    setIsLoading(true);
    setQuestion(""); // Clear input
    setMessages(prev => [...prev, { sender: 'user', text: queryText }]);

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
        body: JSON.stringify({ question: queryText }),
      });

      let botResponse = "";
      if (res.ok) {
        const data = await res.json();
        botResponse = data.answer;
      } else if (res.status === 401) {
        botResponse = "Your session has expired. Please log in again.";
        setTimeout(() => handleLogout(), 3000);
      } else {
        const errData = await res.json();
        botResponse = `Sorry, an error occurred: ${errData.detail}`;
      }
      
      // Add bot response to chat
      setMessages(prev => [...prev, { sender: 'bot', text: botResponse }]);
      
      // --- Read the response aloud ---
      speak(botResponse);

    } catch (error) {
      console.error("Failed to fetch:", error);
      const errorMsg = "Sorry, I couldn't connect to the bot.";
      setMessages(prev => [...prev, { sender: 'bot', text: errorMsg }]);
      speak(errorMsg);
    }
    
    setIsLoading(false);
  };

  // --- Form submit for typed text ---
  const handleFormSubmit = (e) => {
    e.preventDefault();
    sendQuery(question);
  };

  // --- Button click for microphone ---
  const handleListenClick = () => {
    if (!recognition || isListening) return;

    recognition.onstart = () => {
      setIsListening(true);
    };
    
    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      setQuestion(transcript); // Show what was heard
      sendQuery(transcript);   // Automatically send it
    };
    
    recognition.onerror = (event) => {
      console.error("Speech recognition error", event.error);
      setIsListening(false);
    };
    
    recognition.onend = () => {
      setIsListening(false);
    };

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
        <button 
          type="button" 
          className={`mic-button ${isListening ? 'listening' : ''}`}
          onClick={handleListenClick}
          disabled={!recognition || isLoading}
        >
          {isListening ? '...' : '🎙️'}
        </button>
        <button type="submit" className="send-button" disabled={isLoading}>
          ➤
        </button>
      </form>
    </div>
  );
}

export default Chatbot;