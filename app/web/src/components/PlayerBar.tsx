import { useState } from "react";
import { usePlayer, YOUTUBE_CONTAINER_ID } from "../stores/player";

const ENGINE_GLYPH: Record<string, string> = {
  spotify_sdk: "Spotify",
  spotify_embed: "Spotify preview",
  youtube: "YouTube",
  musickit: "Apple Music",
  audio: "Podcast",
};

// Podcast/YouTube speed steps, cycled by the rate button.
const RATES = [1, 1.25, 1.5, 1.75, 2, 0.75];

function fmt(s: number): string {
  if (!Number.isFinite(s) || s <= 0) return "0:00";
  const m = Math.floor(s / 60);
  return `${m}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
}

/** Persistent bottom player bar + in-page theater panel (Part 2 §4.5).
    Audio persists across navigation; video renders in the theater. */
export function PlayerBar() {
  const p = usePlayer();
  const [queueOpen, setQueueOpen] = useState(false);
  const active = p.request !== null && p.option !== null;
  const isYouTube = p.option?.engine === "youtube";
  const audioOnly = p.request?.audioOnly ?? false;
  // Show the video theater only for actual video (trailers, YouTube videos) —
  // songs play audio-only with the iframe parked off-screen.
  const showTheater = active && isYouTube && !audioOnly;
  const isEmbed = p.option?.engine === "spotify_embed";
  const canTransport =
    p.option?.engine === "youtube" ||
    p.option?.engine === "spotify_sdk" ||
    p.option?.engine === "audio" ||
    p.option?.engine === "musickit";

  return (
    <>
      {p.toast && (
        <div
          role="status"
          aria-live="polite"
          className="fixed bottom-24 left-1/2 z-50 -translate-x-1/2 rounded-[6px] border border-line bg-bg2 px-4 py-2 text-[0.875rem]"
        >
          {p.toast}
        </div>
      )}

      {/* YouTube slot — must stay mounted AND visible for the iframe API to play
          (an off-screen/hidden player won't start). Full theater for videos and
          trailers; a small unobtrusive player for songs (YouTube can't do
          audio-only, so we shrink the video rather than hide it). */}
      <div
        className={
          showTheater
            ? "fixed bottom-[88px] right-4 z-40 block w-[min(480px,calc(100vw-2rem))] overflow-hidden rounded-[10px] border border-line bg-black"
            : active && isYouTube
              ? "fixed bottom-[80px] right-3 z-40 block w-[168px] overflow-hidden rounded-[8px] border border-line bg-black shadow-lg"
              : "hidden"
        }
      >
        <div className="aspect-video w-full">
          <div id={YOUTUBE_CONTAINER_ID} className="h-full w-full" />
        </div>
      </div>
      {active && isEmbed && p.option?.payload.track_id && (
        <div className="fixed bottom-[88px] right-4 z-40 w-[min(420px,calc(100vw-2rem))] overflow-hidden rounded-[10px] border border-line">
          <iframe
            title="Spotify preview"
            src={`https://open.spotify.com/embed/track/${p.option.payload.track_id}`}
            width="100%"
            height="80"
            allow="encrypted-media"
          />
        </div>
      )}

      {/* Up-next panel: jump to any queued track, nudge order with ↑/↓. Sits
          higher when the mini YouTube player occupies the corner. */}
      {active && queueOpen && p.queue.length > 0 && (
        <div
          className={`fixed right-4 z-40 max-h-[50vh] w-[min(360px,calc(100vw-2rem))] overflow-y-auto rounded-[10px] border border-line bg-bg1 shadow-lg ${
            isYouTube && audioOnly ? "bottom-[190px]" : "bottom-[88px]"
          }`}
        >
          <p className="sticky top-0 border-b border-line bg-bg1 px-3 py-2 font-mono text-[0.7rem] tracking-widest text-muted">
            UP NEXT · {p.queueIndex + 1}/{p.queue.length}
          </p>
          {p.queue.map((q, i) => (
            <div
              key={`${q.title}-${i}`}
              className={`flex items-center gap-1.5 px-3 py-1.5 ${
                i === p.queueIndex ? "bg-owned/10" : "hover:bg-bg2"
              }`}
            >
              <button
                onClick={() => p.jumpTo(i)}
                className="min-w-0 flex-1 cursor-pointer text-left"
                aria-label={`Play ${q.title}`}
              >
                <p className={`truncate text-[0.85rem] ${i === p.queueIndex ? "text-owned" : ""}`}>
                  {q.title}
                </p>
                <p className="truncate font-mono text-[0.68rem] text-muted">{q.subtitle}</p>
              </button>
              <button
                onClick={() => p.moveInQueue(i, i - 1)}
                disabled={i === 0}
                aria-label={`Move ${q.title} up`}
                className="rounded px-1 font-mono text-[0.8rem] text-muted hover:bg-bg2 hover:text-ink disabled:opacity-25"
              >
                ↑
              </button>
              <button
                onClick={() => p.moveInQueue(i, i + 1)}
                disabled={i === p.queue.length - 1}
                aria-label={`Move ${q.title} down`}
                className="rounded px-1 font-mono text-[0.8rem] text-muted hover:bg-bg2 hover:text-ink disabled:opacity-25"
              >
                ↓
              </button>
            </div>
          ))}
        </div>
      )}

      {active && (
        <div
          className="fixed inset-x-0 bottom-0 z-40 flex h-14 items-center gap-3 border-t border-line bg-bg1 px-3
                     min-[700px]:left-[64px] min-[700px]:h-[72px] min-[700px]:px-4 min-[1100px]:left-[200px]"
        >
          {p.request?.artwork ? (
            <img src={p.request.artwork} alt="" className="h-9 w-9 rounded object-cover min-[700px]:h-11 min-[700px]:w-11" />
          ) : (
            <div className="flex h-9 w-9 items-center justify-center rounded bg-bg2 text-muted min-[700px]:h-11 min-[700px]:w-11">♪</div>
          )}
          <div className="min-w-0 flex-1 min-[700px]:flex-none min-[700px]:w-56">
            <p className="truncate text-[0.875rem]">{p.request?.title}</p>
            <p className="truncate font-mono text-[0.7rem] text-muted">{p.request?.subtitle}</p>
          </div>

          <button
            onClick={p.prev}
            disabled={p.queueIndex <= 0}
            aria-label="Previous track"
            className="hidden h-9 w-9 items-center justify-center rounded-full text-[0.9rem] text-muted hover:bg-bg2 hover:text-ink disabled:opacity-25 min-[700px]:flex"
          >
            ⏮
          </button>
          <button
            onClick={p.toggle}
            disabled={!canTransport}
            aria-label={p.status === "playing" ? "Pause" : "Play"}
            className="flex h-10 w-10 items-center justify-center rounded-full border border-line text-[1rem] hover:bg-bg2 disabled:opacity-30"
          >
            {p.status === "loading" ? "…" : p.status === "playing" ? "⏸" : "▶"}
          </button>
          <button
            onClick={p.next}
            disabled={p.queueIndex < 0 || p.queueIndex >= p.queue.length - 1}
            aria-label="Next track"
            className="hidden h-9 w-9 items-center justify-center rounded-full text-[0.9rem] text-muted hover:bg-bg2 hover:text-ink disabled:opacity-25 min-[700px]:flex"
          >
            ⏭
          </button>

          <div className="hidden flex-1 items-center gap-2 min-[700px]:flex">
            <span className="font-mono text-[0.7rem] text-muted">{fmt(p.position)}</span>
            <input
              type="range"
              min={0}
              max={Math.max(p.duration, 1)}
              value={Math.min(p.position, p.duration || 0)}
              onChange={(e) => p.seek(Number(e.target.value))}
              disabled={!canTransport}
              aria-label="Seek"
              className="h-1 flex-1 accent-[var(--owned)] disabled:opacity-30"
            />
            <span className="font-mono text-[0.7rem] text-muted">{fmt(p.duration)}</span>
          </div>

          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={p.volume}
            onChange={(e) => p.setVolume(Number(e.target.value))}
            disabled={!canTransport}
            aria-label="Volume"
            className="hidden w-20 accent-[var(--owned)] min-[900px]:block disabled:opacity-30"
          />

          {/* Playback speed — podcasts & YouTube only (Spotify's SDK can't). */}
          {(p.option?.engine === "audio" || p.option?.engine === "youtube") && (
            <button
              onClick={() => p.setRate(RATES[(RATES.indexOf(p.rate) + 1) % RATES.length])}
              aria-label={`Playback speed ${p.rate}×`}
              title="Playback speed"
              className="hidden rounded-[6px] border border-line px-1.5 py-0.5 font-mono text-[0.7rem] text-muted hover:bg-bg2 hover:text-ink min-[700px]:block"
            >
              {p.rate}×
            </button>
          )}

          {p.queue.length > 1 && (
            <button
              onClick={() => setQueueOpen((o) => !o)}
              aria-pressed={queueOpen}
              aria-label="Up next"
              title="Up next"
              className={`hidden rounded-[6px] border border-line px-2 py-0.5 font-mono text-[0.7rem] hover:bg-bg2 min-[700px]:block ${
                queueOpen ? "bg-owned/15 text-owned" : "text-muted hover:text-ink"
              }`}
            >
              ≡ {p.queueIndex + 1}/{p.queue.length}
            </button>
          )}

          <span
            className="hidden font-mono text-[0.7rem] text-[color:var(--play)] min-[700px]:block"
            title={p.resolvedVia
              ? `This track had no in-app source, so the best match on ${p.resolvedVia} is playing instead`
              : undefined}
          >
            {ENGINE_GLYPH[p.option?.engine ?? ""] ?? ""}
            {p.resolvedVia && <span className="text-muted"> · best match</span>}
          </span>

          <button
            onClick={p.stop}
            aria-label="Stop playback"
            className="rounded px-2 py-1 font-mono text-[0.8rem] text-muted hover:bg-bg2 hover:text-ink"
          >
            ✕
          </button>
        </div>
      )}
    </>
  );
}
