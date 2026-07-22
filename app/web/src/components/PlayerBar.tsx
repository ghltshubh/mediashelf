import { usePlayer, YOUTUBE_CONTAINER_ID } from "../stores/player";

const ENGINE_GLYPH: Record<string, string> = {
  spotify_sdk: "Spotify",
  spotify_embed: "Spotify preview",
  youtube: "YouTube",
  musickit: "Apple Music",
  audio: "Podcast",
};

function fmt(s: number): string {
  if (!Number.isFinite(s) || s <= 0) return "0:00";
  const m = Math.floor(s / 60);
  return `${m}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
}

/** Persistent bottom player bar + in-page theater panel (Part 2 §4.5).
    Audio persists across navigation; video renders in the theater. */
export function PlayerBar() {
  const p = usePlayer();
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
    p.option?.engine === "audio";

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

      {/* YouTube slot — must stay mounted for the iframe API. Visible theater for
          videos/trailers; for audio-only songs it's parked off-screen but alive,
          so audio keeps playing without showing the video. */}
      <div
        className={
          showTheater
            ? "fixed bottom-[88px] right-4 z-40 block w-[min(480px,calc(100vw-2rem))] overflow-hidden rounded-[10px] border border-line bg-black"
            : "pointer-events-none fixed -left-[9999px] top-0 h-[135px] w-[240px] overflow-hidden opacity-0"
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

          <span className="hidden font-mono text-[0.7rem] text-[color:var(--play)] min-[700px]:block">
            {ENGINE_GLYPH[p.option?.engine ?? ""] ?? ""}
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
