import { useT } from "../lib/i18n";
import { useOnline } from "../lib/useOnline";

/** Slim top strip shown only while offline. The catalog still renders from the
    service worker's cache; this just tells the user the data is last-synced. */
export function OfflineBanner() {
  const online = useOnline();
  const t = useT();
  if (online) return null;
  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed inset-x-0 top-0 z-50 border-b border-line bg-bg2 px-4 py-1.5 text-center font-mono text-[0.72rem] text-muted"
    >
      <span aria-hidden className="mr-1.5 text-[color:var(--elsewhere)]">●</span>
      {t("offline.banner")}
    </div>
  );
}
