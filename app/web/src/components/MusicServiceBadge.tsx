import type { MusicResult } from "../lib/api";

/** Which service a music row plays from — the default playback engine's service,
    else the first listed service. */
export function musicSource(item: MusicResult): string | null {
  return item.playback?.default?.service_key ?? item.services?.[0]?.service_key ?? null;
}

/** Small brand mark for a music service, drawn inline (no external assets, no
    catalog logo needed — music services carry none). Spotify / YouTube Music /
    Apple Music are recognizable; anything else falls back to a neutral ♪ chip. */
export function MusicServiceBadge({
  serviceKey,
  className = "",
}: {
  serviceKey: string | null;
  className?: string;
}) {
  const common = `block h-full w-full`;
  let mark: React.ReactNode;
  let label: string;

  if (serviceKey === "spotify") {
    label = "Spotify";
    mark = (
      <svg viewBox="0 0 24 24" className={common} aria-hidden>
        <circle cx="12" cy="12" r="12" fill="#1ed760" />
        <path
          d="M6.3 15c3.2-1 7.4-.8 10.9 1.2M6.8 11.6c4.2-1.2 9.4-.5 12.4 1.6M7.2 8.1c4.8-1.1 10.6-.1 13.3 2"
          stroke="#000" strokeWidth="1.5" fill="none" strokeLinecap="round"
        />
      </svg>
    );
  } else if (serviceKey === "youtube" || serviceKey === "youtube_music") {
    label = "YouTube Music";
    mark = (
      <svg viewBox="0 0 24 24" className={common} aria-hidden>
        <circle cx="12" cy="12" r="12" fill="#ff0000" />
        <circle cx="12" cy="12" r="7" fill="none" stroke="#fff" strokeWidth="1.6" />
        <path d="M10.2 8.8 15 12l-4.8 3.2z" fill="#fff" />
      </svg>
    );
  } else if (serviceKey === "apple_music") {
    label = "Apple Music";
    mark = (
      <svg viewBox="0 0 24 24" className={common} aria-hidden>
        <rect width="24" height="24" rx="6" fill="#fa233b" />
        <path
          d="M15.5 6.8 10 8.1v6.4a2.2 2.2 0 1 1-1.1-1.9V8.9l5-1.2v4.2a2.2 2.2 0 1 1-1.1-1.9V6.8z"
          fill="#fff"
        />
      </svg>
    );
  } else {
    label = "Music";
    mark = (
      <span className="flex h-full w-full items-center justify-center rounded-full bg-bg0 text-[0.6rem] text-muted">
        ♪
      </span>
    );
  }

  return (
    <span
      title={label}
      aria-label={label}
      className={`inline-flex overflow-hidden rounded-full ${className}`}
    >
      {mark}
    </span>
  );
}
