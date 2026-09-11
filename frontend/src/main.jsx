import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { AuthProvider } from "./AuthContext";
import { CountsProvider } from "./CountsContext";
import { GenerationProvider } from "./GenerationContext";
import { ToastProvider } from "./ToastContext";
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/components.css";
import "./styles/shell.css";
import "./styles/pages.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    {/* useTransitions={false}: route changes commit synchronously, which is what lets
        lib/transitions.js wrap a navigation in document.startViewTransition(). */}
    <BrowserRouter useTransitions={false}>
      <AuthProvider>
        <ToastProvider>
          <CountsProvider>
            <GenerationProvider>
              <App />
            </GenerationProvider>
          </CountsProvider>
        </ToastProvider>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>
);
