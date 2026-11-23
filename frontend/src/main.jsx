import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
// Fontes servidas pelo próprio site (a CSP só aceita font-src 'self')
import "@fontsource-variable/manrope/wght.css";
import "@fontsource-variable/space-grotesk/wght.css";
import "@fontsource-variable/jetbrains-mono/wght.css";
import App from "./App";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
