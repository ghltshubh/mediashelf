import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type MusicResult } from "../lib/api";
import { useActivate } from "../lib/searchData";
import { MusicServiceBadge, musicSource } from "./MusicServiceBadge";

export function MusicCard({ item, onPlay }: { item: MusicResult; onPlay: () => void }) {
  return (
    <button
      onClick={onPlay}
      className="hoverable group w-[132px] shrink-0 cursor-pointer rounded-[10px] bg-bg1 p-2 text-left hover:bg-bg2"
      title={`Play ${item.title}`}
    >
      <div className="relative aspect-square w-full overflow-hidden rounded-[6px] bg-bg2">
        {item.thumb ? (
          <img src={item.thumb} alt="" className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full items-center justify-center text-muted">♪</div>
        )}
        {/* Which app this track plays from, bottom-right of the cover. */}
        <MusicServiceBadge
          serviceKey={musicSource(item)}
          className="absolute bottom-1 right-1 h-4 w-4 shadow-[0_1px_3px_rgba(0,0,0,0.6)]"
        />
        <span
          aria-hidden
          className="absolute inset-0 flex items-center justify-center bg-bg0/0 text-[1.6rem] text-[color:var(--play)] opacity-0 transition-opacity group-hover:bg-bg0/40 group-hover:opacity-100"
        >
          ▶
        </span>
      </div>
      <p className="mt-1.5 truncate text-[0.8rem] leading-tight">{item.title}</p>
      <p className="truncate font-mono text-[0.7rem] text-muted">{item.artists.join(", ")}</p>
    </button>
  );
}

/** Shelf music rail (Part 2 §4.2 lists Music among shelf rows): your synced
    likes, playable in place. Quietly absent until a music account is connected.
    In the by-service view it renders under the service's own name. */
export function MusicRail({ label = "Music" }: { label?: string }) {
  const library = useQuery({ queryKey: ["library"], queryFn: api.library, staleTime: 60_000 });
  const { activate } = useActivate();
  // Liked songs across every connected music source (Spotify + YouTube Music).
  const groups = (library.data?.groups ?? []).filter(
    (g) => g.key === "spotify_like" || g.key === "youtube_music",
  );
  // Round-robin interleave so the visible slice shows every source — otherwise a
  // large Spotify library would fill all 20 shown cards and hide YouTube Music.
  const lists = groups.map((g) => g.items);
  const items: typeof lists[number] = [];
  for (let i = 0; i < Math.max(0, ...lists.map((l) => l.length)); i++) {
    for (const l of lists) if (i < l.length) items.push(l[i]);
  }
  const total = groups.reduce((n, g) => n + g.count, 0);
  if (items.length === 0) return null;
  const shown = items.slice(0, 20);

  return (
    <section className="mb-10">
      <div className="mb-3 flex items-baseline gap-3">
        <Link
          to="/?tab=music"
          className="group flex items-baseline gap-1.5 font-display text-[1.25rem] font-semibold hover:text-owned"
        >
          <span className="underline decoration-line decoration-1 underline-offset-4 group-hover:decoration-[var(--owned)]">
            {label}
          </span>
          <span aria-hidden className="text-[1rem] text-muted group-hover:text-owned">›</span>
        </Link>
        <Link to="/library" className="font-mono text-[0.75rem] text-muted hover:text-owned">
          your library · {total} liked →
        </Link>
      </div>
      <div className="rail flex gap-4 overflow-x-auto pb-4 pt-1">
        {shown.map((item, i) => (
          // Queue spans every source (Spotify + YouTube Music), so playback runs
          // continuously across apps once started from the Music rail.
          <MusicCard key={i} item={item} onPlay={() => void activate(item, undefined, items)} />
        ))}
      </div>
    </section>
  );
}
