import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { GlobalLoadingBar } from "./components/GlobalLoadingBar";
import { OfflineBanner } from "./components/OfflineBanner";
import { PlayerBar } from "./components/PlayerBar";
import { SearchPalette } from "./components/SearchPalette";
import { Sidebar } from "./components/Sidebar";
import { api } from "./lib/api";
import { usePalette } from "./stores/palette";
import { Browse } from "./pages/Browse";
import { DevComponents } from "./pages/DevComponents";
import { Library } from "./pages/Library";
import { Migrations } from "./pages/Migrations";
import { Onboarding } from "./pages/Onboarding";
import { Person } from "./pages/Person";
import { SearchResults } from "./pages/SearchResults";
import { Settings } from "./pages/Settings";
import { Shelf } from "./pages/Shelf";
import { TitlePage } from "./pages/Title";

function isTypingTarget(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false;
  return (
    el.tagName === "INPUT" ||
    el.tagName === "TEXTAREA" ||
    el.tagName === "SELECT" ||
    el.isContentEditable
  );
}

export function App() {
  const location = useLocation();
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const { toggle, openPalette } = usePalette();

  // Search reachable from every page via Cmd/Ctrl-K or "/" (product acceptance).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        toggle();
      } else if (e.key === "/" && !isTypingTarget(e.target)) {
        e.preventDefault();
        openPalette();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggle, openPalette]);

  const needsOnboarding =
    settings.data && !settings.data.onboarded && !settings.data.tmdb_api_key_set;
  if (location.pathname === "/onboarding") {
    return (
      <main className="min-h-screen px-6 pb-16">
        <Onboarding />
      </main>
    );
  }
  if (needsOnboarding) {
    return <Navigate to="/onboarding" replace />;
  }

  return (
    <div className="min-h-screen">
      <GlobalLoadingBar />
      <OfflineBanner />
      <Sidebar />
      <SearchPalette />
      <PlayerBar />
      <main className="px-5 pb-32 pt-6 min-[700px]:ml-[64px] min-[700px]:pb-28 min-[700px]:px-8 min-[1100px]:ml-[200px]">
        <Routes>
          <Route path="/" element={<Shelf />} />
          <Route path="/title/:id" element={<TitlePage />} />
          <Route path="/person/:id" element={<Person />} />
          <Route path="/browse/:railKey" element={<Browse />} />
          <Route path="/search" element={<SearchResults />} />
          <Route path="/library" element={<Library />} />
          <Route path="/migrations" element={<Migrations />} />
          <Route path="/settings" element={<Settings />} />
          {import.meta.env.DEV && <Route path="/dev/components" element={<DevComponents />} />}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
