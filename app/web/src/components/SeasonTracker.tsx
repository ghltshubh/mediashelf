import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, type SeasonProgress, type ShowState } from "../lib/api";

const STATE_LABEL: Record<ShowState, string> = {
  not_started: "",
  watching: "",
  caught_up: "caught up",
  seen: "seen",
};

/** Episode progress for a show (issue #2).
 *
 * Marking is manual on purpose: MediaShelf deep-links out for TV, so the
 * viewing happens inside Netflix or Prime and nothing reports back. A Plex or
 * Trakt connector would write into the same store and light these boxes up on
 * its own — the UI does not need to change for that to work.
 *
 * Collapsed by default. Someone who tracks nothing should see one quiet line,
 * not an episode grid pushed between them and the availability block.
 */
export function SeasonTracker({ itemId }: { itemId: number }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [season, setSeason] = useState<number | null>(null);

  const progress = useQuery({
    queryKey: ["seasons", itemId],
    queryFn: () => api.seasons(itemId),
  });

  // Open on wherever they left off, so resuming a show costs no clicks.
  useEffect(() => {
    if (season === null && progress.data) {
      setSeason(progress.data.next_up?.season ?? progress.data.seasons[0]?.season_number ?? null);
    }
  }, [progress.data, season]);

  const episodes = useQuery({
    queryKey: ["episodes", itemId, season],
    queryFn: () => api.seasonEpisodes(itemId, season!),
    enabled: open && season !== null,
  });

  const write = useMutation({
    mutationFn: ({ s, eps, watched }: { s: number; eps: number[]; watched: boolean }) =>
      api.setWatched(itemId, s, eps, watched),
    onSuccess: (data: SeasonProgress) => {
      qc.setQueryData(["seasons", itemId], data);
      qc.invalidateQueries({ queryKey: ["episodes", itemId] });
    },
  });

  const clear = useMutation({
    mutationFn: () => api.clearWatched(itemId),
    onSuccess: (data: SeasonProgress) => {
      qc.setQueryData(["seasons", itemId], data);
      qc.invalidateQueries({ queryKey: ["episodes", itemId] });
    },
  });

  const p = progress.data;
  if (!p || p.seasons.length === 0) return null;

  const pct = p.total_episodes ? Math.round((p.watched_episodes / p.total_episodes) * 100) : 0;
  const current = p.seasons.find((s) => s.season_number === season);
  const seasonAllWatched = current ? current.watched_count >= current.episode_count : false;
  const busy = write.isPending || clear.isPending;

  return (
    <section className="mt-8 max-w-2xl">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 className="font-mono text-[0.75rem] tracking-widest text-muted">EPISODES</h2>
        <span className="font-mono text-[0.75rem] text-muted">
          {p.watched_episodes}/{p.total_episodes} watched
          {STATE_LABEL[p.state] && (
            <span className={`ml-2 ${p.state === "watching" ? "text-muted" : "text-owned"}`}>
              · {STATE_LABEL[p.state]}
            </span>
          )}
        </span>
      </div>

      {/* Progress bar doubles as the "where am I" answer at a glance. */}
      <div className="mt-2 h-[3px] w-full overflow-hidden rounded-full bg-bg2">
        <div className="h-full rounded-full bg-owned transition-[width] duration-300"
             style={{ width: `${pct}%` }} />
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-3">
        {/* Only offer "next up" when that episode actually exists. Being caught
            up on a running show would otherwise point at an unaired episode. */}
        {p.state === "watching" && p.next_up && (
          <button
            disabled={busy}
            onClick={() => {
              setOpen(true);
              setSeason(p.next_up!.season);
            }}
            className="hoverable rounded-[6px] border border-line px-3 py-1.5 font-mono text-[0.8rem] hover:bg-bg2 disabled:opacity-50"
          >
            Next up · S{p.next_up.season} E{p.next_up.episode}
          </button>
        )}
        {p.state === "caught_up" && (
          <span className="font-mono text-[0.8rem] text-muted">
            Up to date
            {p.next_air_date ? ` — next episode ${p.next_air_date}` : ""}
          </span>
        )}
        {p.state === "seen" && (
          <span className="font-mono text-[0.8rem] text-muted">Every episode marked.</span>
        )}
        <button
          onClick={() => setOpen((v) => !v)}
          className="hoverable rounded-[6px] px-2 py-1 font-mono text-[0.8rem] text-muted hover:bg-bg2 hover:text-ink"
        >
          {open ? "Hide episodes" : "Track episodes"}
        </button>
        {open && p.watched_episodes > 0 && (
          <button
            disabled={busy}
            onClick={() => clear.mutate()}
            className="hoverable rounded-[6px] px-2 py-1 font-mono text-[0.8rem] text-muted hover:bg-bg2 hover:text-ink disabled:opacity-50"
          >
            Reset
          </button>
        )}
      </div>

      {open && (
        <div className="mt-4 rounded-[10px] border border-line bg-bg1 p-3">
          <div className="flex flex-wrap gap-1.5">
            {p.seasons.map((s) => (
              <button
                key={s.season_number}
                onClick={() => setSeason(s.season_number)}
                className={`hoverable rounded-[6px] px-2.5 py-1 font-mono text-[0.75rem] ${
                  s.season_number === season
                    ? "bg-owned text-bg0"
                    : "border border-line text-muted hover:bg-bg2 hover:text-ink"
                }`}
              >
                S{s.season_number}
                <span className={s.season_number === season ? "opacity-70" : "opacity-60"}>
                  {" "}
                  {s.watched_count}/{s.episode_count}
                </span>
              </button>
            ))}
          </div>

          {season !== null && current && (
            <div className="mt-3 flex justify-end">
              <button
                disabled={busy || current.episode_count === 0}
                onClick={() =>
                  write.mutate({
                    s: season,
                    eps: Array.from({ length: current.episode_count }, (_, i) => i + 1),
                    watched: !seasonAllWatched,
                  })
                }
                className="hoverable rounded-[6px] px-2 py-1 font-mono text-[0.75rem] text-muted hover:bg-bg2 hover:text-ink disabled:opacity-50"
              >
                {seasonAllWatched ? "Unmark whole season" : "Mark whole season"}
              </button>
            </div>
          )}

          <div className="mt-2 space-y-1">
            {episodes.isPending && (
              <div className="space-y-1">
                {[0, 1, 2].map((i) => (
                  <div key={i} className="h-9 animate-pulse rounded-[6px] bg-bg2" />
                ))}
              </div>
            )}
            {episodes.data?.episodes.length === 0 && (
              <p className="px-1 py-2 text-[0.85rem] text-muted">
                TMDB lists no episodes for this season yet.
              </p>
            )}
            {episodes.data?.episodes.map((ep) => (
              <button
                key={ep.episode_number}
                disabled={busy}
                onClick={() =>
                  write.mutate({ s: season!, eps: [ep.episode_number], watched: !ep.watched })
                }
                className={`hoverable flex w-full items-center gap-3 rounded-[6px] px-2 py-1.5 text-left hover:bg-bg2 disabled:opacity-50 ${
                  ep.watched ? "text-muted" : "text-ink"
                }`}
              >
                {/* The tick is the control — the whole row is the hit target. */}
                <span
                  aria-hidden
                  className={`flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-[4px] border text-[0.7rem] ${
                    ep.watched ? "border-owned bg-owned text-bg0" : "border-line"
                  }`}
                >
                  {ep.watched ? "✓" : ""}
                </span>
                <span className="w-8 shrink-0 font-mono text-[0.75rem] text-muted">
                  E{ep.episode_number}
                </span>
                <span className={`min-w-0 flex-1 truncate text-[0.9rem] ${ep.watched ? "line-through" : ""}`}>
                  {ep.name ?? `Episode ${ep.episode_number}`}
                </span>
                {ep.runtime_minutes && (
                  <span className="shrink-0 font-mono text-[0.7rem] text-muted">
                    {ep.runtime_minutes}m
                  </span>
                )}
              </button>
            ))}
          </div>

          {/* Say why this is manual, once, where the question actually arises. */}
          <p className="mt-3 border-t border-line pt-2 font-mono text-[0.68rem] leading-relaxed text-muted/70">
            You mark these yourself — MediaShelf links you out to the service and
            can't see what you finished there.
          </p>
        </div>
      )}
    </section>
  );
}
