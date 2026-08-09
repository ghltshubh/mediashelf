import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { ShelfItem } from "../lib/api";
import { api } from "../lib/api";
import { MediaCard } from "./MediaCard";

/** A Continue-watching card with a one-tap "I watched that" tick.
 *
 * The common move on this rail is "finished an episode, mark it, move on" —
 * making that a page visit is three clicks for a one-bit fact, which is why
 * Jellyfin puts the control on the card. The difference here is what a card
 * means: this is a *show*, so a bare "mark watched" would be forty episodes in
 * one tap. The tick therefore marks the NEXT episode and the card advances,
 * which is both the useful action and a safe one to mis-tap.
 *
 * MediaCard is a <Link>, so the button is a sibling in a wrapper rather than a
 * child — a <button> inside an <a> is invalid and breaks keyboard use.
 */
export function ContinueWatchingCard({ item }: { item: ShelfItem }) {
  const qc = useQueryClient();
  const next = item.next_up ?? null;

  const mark = useMutation({
    mutationFn: () => api.setWatched(item.id, next!.season, [next!.episode], true),
    onSuccess: () => {
      // The rail itself has to recompute: this may have been the last aired
      // episode, in which case the show is caught up and leaves the rail.
      qc.invalidateQueries({ queryKey: ["shelf"] });
      qc.invalidateQueries({ queryKey: ["seasons", item.id] });
      qc.invalidateQueries({ queryKey: ["episodes", item.id] });
    },
  });

  const label = next ? `S${next.season} E${next.episode}` : "";
  const remaining = item.unwatched_aired ?? 0;

  return (
    // The wrapper carries the rail's card width, and MediaCard fills it — the
    // card is no longer a flex child of the rail, so it can't size itself.
    <div className="relative w-[148px] shrink-0 sm:w-[168px]">
      <MediaCard item={item} fluid />
      {next && (
        <button
          type="button"
          disabled={mark.isPending}
          onClick={() => mark.mutate()}
          title={`Mark ${label} watched`}
          aria-label={`Mark ${item.title} ${label} watched`}
          // Always visible, not hover-only: it has to be reachable on touch,
          // and it is the reason to come to this rail at all.
          className="hoverable absolute right-1.5 top-1.5 flex h-7 items-center gap-1 rounded-full border border-line bg-bg0/75 px-2 font-mono text-[0.7rem] text-ink/90 opacity-80 backdrop-blur-[2px] transition hover:border-owned hover:text-owned hover:opacity-100 focus-visible:opacity-100 disabled:opacity-40"
        >
          <span aria-hidden>✓</span>
          {label}
        </button>
      )}
      {/* Progress under the card: the rail's whole job is "where am I". */}
      {next && (
        <p className="px-2 pb-1 font-mono text-[0.68rem] text-muted">
          {remaining > 0 ? `${remaining} waiting` : "up to date"}
        </p>
      )}
    </div>
  );
}
