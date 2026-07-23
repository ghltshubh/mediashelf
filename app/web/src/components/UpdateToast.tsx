import { useEffect, useState } from "react";
import { useT } from "../lib/i18n";

/** "New version ready" toast. main.tsx fires mediashelf:sw-updated when a new
    service worker takes over while this page still runs the old bundle — one
    click reloads into the fresh build instead of silently serving stale UI. */
export function UpdateToast() {
  const [show, setShow] = useState(false);
  const t = useT();

  useEffect(() => {
    const on = () => setShow(true);
    window.addEventListener("mediashelf:sw-updated", on);
    return () => window.removeEventListener("mediashelf:sw-updated", on);
  }, []);

  if (!show) return null;
  return (
    <div
      role="status"
      className="fixed bottom-20 left-1/2 z-50 flex -translate-x-1/2 items-center gap-3 rounded-[8px] border border-line bg-bg2 px-4 py-2 text-[0.875rem] shadow-lg"
    >
      {t("update.ready")}
      <button
        onClick={() => window.location.reload()}
        className="rounded-[6px] bg-owned px-3 py-1 font-medium text-bg0"
      >
        {t("update.reload")}
      </button>
      <button
        onClick={() => setShow(false)}
        aria-label={t("common.dismiss")}
        className="rounded px-1 font-mono text-[0.8rem] text-muted hover:text-ink"
      >
        ✕
      </button>
    </div>
  );
}
