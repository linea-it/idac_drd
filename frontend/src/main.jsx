import { CssBaseline, ThemeProvider } from "@mui/material";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import Assignees from "./pages/Assignees";
import AuthGate from "./components/AuthGate";
import Analytics from "./pages/Analytics";
import ReleaseBoard from "./pages/ReleaseBoard";
import ReleaseList from "./pages/ReleaseList";
import TemplateEditor from "./pages/TemplateEditor";
import theme from "./theme";

const rootEl = document.getElementById("wkfw-root");
if (rootEl) {
  const authenticated = rootEl.dataset.authenticated === "true";
  const loginUrl = rootEl.dataset.loginUrl || "/admin/login/?next=/";
  const page = rootEl.dataset.page || "releases";
  const releaseSlug = rootEl.dataset.releaseSlug || "";
  const isStaff = rootEl.dataset.isStaff === "true";

  let content = null;
  if (!authenticated) {
    content = <AuthGate loginUrl={loginUrl} />;
  } else if (page === "board") {
    content = <ReleaseBoard releaseSlug={releaseSlug} />;
  } else if (page === "templates") {
    content = <TemplateEditor isStaff={isStaff} />;
  } else if (page === "analytics") {
    content = <Analytics />;
  } else if (page === "assignees") {
    content = <Assignees isStaff={isStaff} />;
  } else {
    content = <ReleaseList />;
  }

  createRoot(rootEl).render(
    <StrictMode>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        {content}
      </ThemeProvider>
    </StrictMode>,
  );
}
