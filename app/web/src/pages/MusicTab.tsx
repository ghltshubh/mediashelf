import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { EmptyState } from "../components/EmptyState";
import { MusicCard } from "../components/MusicRail";
import { api, type MusicResult } from "../lib/api";
import { useActivate } from "../lib/searchData";
import { usePalette } from "../stores/palette";

function ArtistCard({ item, onOpen }: { item: MusicResult; onOpen: () => void }) {
  return (
    <button
      onClick={onOpen}
      className="hoverable w-[110px] shrink-0 rounded-[10px] p-2 text-center hover:bg-bg2"
      title={item.title}
    >
      <div className="mx-auto aspect-square w-[88px] overflow-hidden rounded-full bg-bg2">
        {item.thumb ? (
          <img src={item.thumb} alt="" className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full items-center justify-center text-muted">♪</div>
        )}
      </div>
      <p className="mt-1.5 truncate text-[0.8rem]">{item.title}</p>
    </button>
  );
}

/** The Music tab: music's home on the shelf — your synced library, playable.
    Catalog-wide discovery stays in search until M8's music sources land. */
export function MusicTab() {
  const library = useQuery({ queryKey: ["library"], queryFn: api.library, staleTime: 60_000 });
  const { activate } = useActivate();
  const { openPalette } = usePalette();

  const data = library.data;
  if (!data) return <div className="h-40 animate-pulse rounded-[10px] bg-bg1" />;

  const likes = data.groups.find((g) => g.key === "spotify_like");
  const artists = data.groups.find((g) => g.key === "spotify_follow");
  const anyMusic = (likes?.count ?? 0) + (artists?.count ?? 0) > 0;

  if (!anyMusic) {
    return (
      <EmptyState
        message="Connect Spotify to bring your music here — liked songs and followed artists, playable in place."
        action={
          <Link
            to="/settings#accounts"
            className="inline-block rounded-[6px] bg-owned px-4 py-2 font-medium text-bg0"
          >
            Connect Spotify
          </Link>
        }
      />
    );
  }

  return (
    <div>
      {likes && likes.items.length > 0 && (
        <section className="mb-10">
          <div className="mb-3 flex items-baseline gap-3">
            <h2 className="font-display text-[1.25rem] font-semibold">Liked songs</h2>
            <Link to="/library" className="font-mono text-[0.75rem] text-muted hover:text-owned">
              see all {likes.count} →
            </Link>
          </div>
          <div className="rail flex gap-4 overflow-x-auto pb-4 pt-1">
            {likes.items.slice(0, 24).map((item, i) => (
              <MusicCard key={i} item={item} onPlay={() => void activate(item)} />
            ))}
          </div>
        </section>
      )}

      {artists && artists.items.length > 0 && (
        <section className="mb-10">
          <div className="mb-3 flex items-baseline gap-3">
            <h2 className="font-display text-[1.25rem] font-semibold">Artists you follow</h2>
            <Link to="/library" className="font-mono text-[0.75rem] text-muted hover:text-owned">
              see all {artists.count} →
            </Link>
          </div>
          <div className="rail flex gap-2 overflow-x-auto pb-4 pt-1">
            {artists.items.slice(0, 24).map((item, i) => (
              <ArtistCard key={i} item={item} onOpen={() => void activate(item)} />
            ))}
          </div>
        </section>
      )}

      <p className="font-mono text-[0.8rem] text-muted">
        looking for something else?{" "}
        <button onClick={openPalette} className="text-owned hover:underline">
          search the whole catalog
        </button>{" "}
        — <kbd className="rounded border border-line px-1">⌘K</kbd> from anywhere
      </p>
    </div>
  );
}
