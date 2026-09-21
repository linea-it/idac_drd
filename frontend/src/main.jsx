import { CssBaseline, ThemeProvider } from "@mui/material";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import AuthGate from "./components/AuthGate";
import ReleaseBoard from "./pages/ReleaseBoard";
import ReleaseList from "./pages/ReleaseList";
import theme from "./theme";

const rootEl = document.getElementById("idac-drd-root");
if (rootEl) {
  const authenticated = rootEl.dataset.authenticated === "true";
  const loginUrl = rootEl.dataset.loginUrl || "admin/login/?next=./";
  const page = rootEl.dataset.page || "releases";
  const releaseSlug = rootEl.dataset.releaseSlug || "";
  const isStaff = rootEl.dataset.isStaff === "true";
  const isSuperuser = rootEl.dataset.isSuperuser === "true";
  const userEmail = rootEl.dataset.userEmail || "";

  let content = null;
  if (!authenticated) {
    content = <AuthGate loginUrl={loginUrl} />;
  } else if (page === "board") {
    content = (
      <ReleaseBoard
        releaseSlug={releaseSlug}
        isStaff={isStaff}
        isSuperuser={isSuperuser}
        userEmail={userEmail}
      />
    );
  } else {
    content = <ReleaseList page={page} />;
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
