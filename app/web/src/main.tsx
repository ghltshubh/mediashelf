import "@fontsource-variable/bricolage-grotesque";
import "@fontsource/spline-sans-mono";
import "./index.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 30_000 },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);

// Register the app-shell service worker in production builds only (the Vite dev
// server serves modules a precache would fight with). Failures are non-fatal.
if ("serviceWorker" in navigator && import.meta.env.PROD) {
  window.addEventListener("load", () => {
    navigator.serviceWorker
      .register("/sw.js")
      .then((reg) => {
        // Long-lived tabs should learn about new builds: re-check periodically
        // and whenever the tab regains focus.
        const check = () => void reg.update().catch(() => {});
        window.setInterval(check, 30 * 60 * 1000);
        document.addEventListener("visibilitychange", () => {
          if (document.visibilityState === "visible") check();
        });
      })
      .catch(() => {});
    // A controller swap AFTER initial load means a new version took over while
    // this page still runs the old bundle → surface the reload toast. (The
    // first-ever install also fires controllerchange; the flag skips it.)
    let hadController = !!navigator.serviceWorker.controller;
    navigator.serviceWorker.addEventListener("controllerchange", () => {
      if (hadController) window.dispatchEvent(new Event("mediashelf:sw-updated"));
      hadController = true;
    });
  });
}
