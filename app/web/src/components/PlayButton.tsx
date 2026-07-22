import { useEffect, useRef, useState } from "react";
import type { Playback, PlayOption } from "../lib/api";
import { usePlayer, type PlayRequest } from "../stores/player";

const ENGINE_GLYPH: Record<string, string> = {
  spotify_sdk: "▶",
  musickit: "▶",
  youtube: "▶",
  spotify_embed: "▶",
  deeplink: "↗",
};

/** Primary Play button with service glyph + caret opening the explicit
    "play on…" list (Part 2 §4.4). Dedupe never hides playback choice. */
export function PlayButton({
  playback,
  title,
  subtitle,
  artwork,
}: {
  playback: Playback;
  title: string;
  subtitle: string;
  artwork: string | null;
}) {
  const player = usePlayer();
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (!menuRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  if (!playback.default) return null;
  const d = playback.default;
  const req: PlayRequest = { title, subtitle, artwork, options: playback.options };

  const run = (option: PlayOption) => {
    setOpen(false);
    player.play(req, option);
  };

  return (
    <div className="relative inline-flex" ref={menuRef}>
      <button
        onClick={() => run(d)}
        className="inline-flex items-center gap-2 rounded-l-[6px] bg-owned px-4 py-2 font-medium text-bg0 hover:opacity-90"
      >
        <span aria-hidden>{ENGINE_GLYPH[d.engine]}</span>
        {d.engine === "deeplink" ? `Play on ${d.label}` : `Play · ${d.label}`}
      </button>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label="Choose where to play"
        aria-expanded={open}
        className="rounded-r-[6px] border-l border-bg0/30 bg-owned px-2 py-2 text-bg0 hover:opacity-90"
      >
        ▾
      </button>
      {open && (
        <div className="absolute left-0 top-full z-30 mt-1 w-64 rounded-[10px] border border-line bg-bg2 py-1 shadow-none">
          <p className="px-3 py-1 font-mono text-[0.7rem] tracking-widest text-muted">PLAY ON…</p>
          {playback.options.map((o, i) => (
            <button
              key={`${o.engine}-${o.service_key}-${i}`}
              onClick={() => run(o)}
              className="flex w-full items-center justify-between px-3 py-2 text-left text-[0.875rem] hover:bg-bg1"
            >
              <span>
                <span aria-hidden className="mr-2">{ENGINE_GLYPH[o.engine]}</span>
                {o.label}
              </span>
              <span className="font-mono text-[0.7rem] text-muted">{o.kind}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
