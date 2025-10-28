// src/Login.jsx
import React, { useEffect } from "react";
import "./Login.css";

function Login({ selectedRole, onBack }) {
  const roleTitle = selectedRole
    ? selectedRole.charAt(0).toUpperCase() + selectedRole.slice(1)
    : "User";

  useEffect(() => {
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.defer = true;
    document.body.appendChild(script);

    script.onload = () => {
      if (window.google) {
        window.google.accounts.id.initialize({
          client_id:
            "579116108847-qg7v7hmhmfp098lt886t3gs3l0j25dt8.apps.googleusercontent.com",
          
          // --- THIS IS THE UPDATED CALLBACK FUNCTION ---
          callback: async (response) => {
            
            // The 'response.credential' is the Google JWT
            console.log("✅ Google Sign-In successful. Sending token to backend...");

            try {
              // 1. SEND GOOGLE'S TOKEN TO YOUR BACKEND
              const res = await fetch("http://127.0.0.1:8000/auth/gsi_login", {
                method: "POST",
                headers: {
                  "Content-Type": "application/json",
                },
                // Send the Google token in the body
                body: JSON.stringify({ token: response.credential }),
              });

              // 2. HANDLE THE RESPONSE FROM YOUR SERVER
              if (res.ok) {
                // Your backend successfully verified the user
                const data = await res.json(); // { access_token, role, ... }

                // --- THIS IS THE MOST IMPORTANT CHANGE ---
                // Save YOUR backend's token, not Google's.
                // This token is what you will use for /bot/ask and /ingest/upload
                localStorage.setItem('access_token', data.access_token);
                // ------------------------------------------
                
                // You can also save the email or role if your app needs it
                // localStorage.setItem('user_role', data.role);

                alert(`✅ Login successful! Welcome. Role: ${data.role}`);

                // 3. REDIRECT BASED ON THE ROLE
                if (data.role === "admin") {
                  window.location.href = "/admin-dashboard";
                } else if (data.role === "parent") {
                  window.location.href = "/parent-dashboard";
                } else {
                  window.location.href = "/dashboard"; // For "student"
                }
              } else {
                // Your backend rejected the login (e.g., domain not allowed)
                const { detail } = await res.json();
                alert(`⚠️ Login Failed: ${detail}. Please use an organization email.`);
              }
            } catch (error) {
              // Server is down or a network error occurred
              console.error("Error connecting to server:", error);
              alert("⚠️ Could not connect to the server. Please try again later.");
            }
          },
          ux_mode: "popup",
        });

        // Render Google button
        const div = document.getElementById("google-signin");
        if (div) {
          window.google.accounts.id.renderButton(div, {
            theme: "outline",
            size: "large",
            width: "100%",
          });
        }
      }
    };

    return () => {
      document.body.removeChild(script);
    };
  }, [selectedRole, roleTitle]);

  return (
    <div className="login-body">
      {/* Back button */}
      <button className="global-back-button" onClick={onBack} type="button">
        <span className="back-arrow">←</span> Back
      </button>

      {/* Login Card */}
      <div className="login-card">
        <h2>{roleTitle} Login</h2>
        
        {/* Your old form (can be removed if only using Google) */}
        {/* <form> ... </form> */}
        {/* <h3 className="or-text">or</h3> */}
        
        <p>Please sign in with your organization's Google account.</p>
        <div id="google-signin"></div>
      </div>
    </div>
  );
}

export default Login;