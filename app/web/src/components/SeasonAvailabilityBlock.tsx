import { useQuery } from "@tanstack/react-query";
import { api, type SeasonOffer } from "../lib/api";
import { ServiceMark } from "./ServiceMark";

/** "Seasons 1–4 on Prime, season 5 on Netflix" (issue #2).
 *
 * The title-level availability block answers for the whole show, which is wrong
 * for one whose seasons moved service. This fills that gap — and only that gap:
 * when every season streams in the same place the block hides itself, because
 * the availability rows above already said so.
 *
 * A season counts as available as soon as a provider carries it, whether or not
 * every episode has aired; a mid-release season is still watchable.
 */
export function SeasonAvailabilityBlock({ itemId, region }: { itemId: number; region: string }) {
  const q = useQuery({
    queryKey: ["season-availability", itemId, region],
    queryFn: () => api.seasonAvailability(itemId, region),
  });

  const data = q.data;
  if (!data || !data.split) return null;

  const rows = (
    <div className="space-y-2">
      {data.groups.map((g) => {
        const visible = visibleOffers(g.offers);
        const hidden = g.offers.length - visible.length;
        return (
          <div
            key={`${g.from}-${g.to}`}
            className={`flex items-center justify-between gap-3 rounded-[6px] border px-3 py-2.5 ${
              g.offers.some((o) => o.owned)
                ? "border-owned/40 bg-owned/[0.07]"
                : "border-line bg-bg1"
            }`}
          >
            <span className="shrink-0 font-mono text-[0.8rem] text-muted">
              {g.from === g.to ? `Season ${g.from}` : `Seasons ${g.from}–${g.to}`}
            </span>
            {g.offers.length > 0 ? (
              <span
                className="flex min-w-0 flex-wrap items-center justify-end gap-x-3 gap-y-1"
                title={g.offers.map((o) => o.service_name).join(", ")}
              >
                {/* Named, not just a logo. A 16px mark is fine on a poster
                    card, but here the whole question is *which* service has
                    season 5 — an unlabelled icon doesn't answer it. */}
                {visible.map((o) => (
                  <span key={o.service_key} className="flex shrink-0 items-center gap-1.5">
                    <ServiceMark name={o.service_name} logo={o.logo} owned={o.owned} />
                    <span className={`text-[0.85rem] ${o.owned ? "text-ink" : "text-muted"}`}>
                      {o.service_name}
                    </span>
                  </span>
                ))}
                {hidden > 0 && (
                  <span className="font-mono text-[0.75rem] text-muted">+{hidden}</span>
                )}
              </span>
            ) : (
              <span className="font-mono text-[0.75rem] text-muted">not reported</span>
            )}
          </div>
        );
      })}
    </div>
  );

  // A 28-season procedural yields ~18 rows, which is a wall rather than an
  // answer. Past a handful, collapse behind a summary — the same treatment the
  // "in other regions" block gets.
  if (data.groups.length <= 6) {
    return (
      <div>
        <h2 className="mb-2 font-mono text-[0.75rem] tracking-widest text-muted">BY SEASON</h2>
        {rows}
      </div>
    );
  }
  const lastSeason = data.groups[data.groups.length - 1].to;
  return (
    <details className="group rounded-[10px] border border-line bg-bg1">
      <summary className="cursor-pointer list-none px-4 py-3 font-mono text-[0.75rem] tracking-widest text-muted hover:text-ink">
        <span className="mr-2 inline-block transition-transform group-open:rotate-90">▸</span>
        BY SEASON · IT MOVES {data.groups.length} TIMES ACROSS {lastSeason} SEASONS
      </summary>
      <div className="px-4 pb-4">{rows}</div>
    </details>
  );
}

/** Every service you pay for, topped up to three with the rest.
 *
 * Some shows list nine near-identical add-on channels per season (Paramount+
 * Essential, Paramount+ Amazon Channel, …), which buries the one you actually
 * subscribe to. The full list stays in the row's tooltip.
 */
function visibleOffers(offers: SeasonOffer[]): SeasonOffer[] {
  const owned = offers.filter((o) => o.owned);
  const rest = offers.filter((o) => !o.owned);
  // Names take more room than icons, so fewer fit before the "+N".
  return [...owned, ...rest].slice(0, Math.max(owned.length, 2));
}
