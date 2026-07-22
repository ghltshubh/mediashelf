/** MediaShelf logomark: media "spines" standing on a shelf, in the brass
    "owned" tone with the lit→dimmed falloff that is the app's core metaphor
    (the front item is fully lit; the rest recede). Pure inline SVG — no assets,
    scales crisply, and inherits the theme via the --owned token. */
export function Logo({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 28 28" className={className} fill="none" role="img" aria-label="MediaShelf">
      {/* the shelf */}
      <rect x="3" y="20.2" width="22" height="2.6" rx="1.3" fill="var(--owned)" />
      {/* media standing on it — front lit, receding dimmer, one leaning */}
      <rect x="5.2" y="9" width="3.3" height="11.2" rx="1.3" fill="var(--owned)" />
      <rect x="9.9" y="5.8" width="3.3" height="14.4" rx="1.3" fill="var(--owned)" opacity="0.72" />
      <rect x="14.6" y="10.6" width="3.3" height="9.6" rx="1.3" fill="var(--owned)" opacity="0.5" />
      <rect
        x="19.3"
        y="8.4"
        width="3.3"
        height="11.8"
        rx="1.3"
        fill="var(--owned)"
        opacity="0.86"
        transform="rotate(11 20.95 14.3)"
      />
    </svg>
  );
}
