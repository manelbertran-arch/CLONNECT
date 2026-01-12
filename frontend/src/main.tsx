import { createRoot } from "react-dom/client";
import App from "./App.tsx";
import "./index.css";

// Debug logging
console.log("[CLONNECT DEBUG] main.tsx loaded");
console.log("[CLONNECT DEBUG] Looking for #root element...");

const rootElement = document.getElementById("root");
if (rootElement) {
  console.log("[CLONNECT DEBUG] Found #root element, mounting React app");
  try {
    createRoot(rootElement).render(<App />);
    console.log("[CLONNECT DEBUG] React app rendered successfully");
  } catch (error) {
    console.error("[CLONNECT DEBUG] Error rendering app:", error);
  }
} else {
  console.error("[CLONNECT DEBUG] FATAL: #root element not found!");
}
