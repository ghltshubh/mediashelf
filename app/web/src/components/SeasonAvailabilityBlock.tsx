import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { ServiceMark } from "./ServiceMark";

/** "Seasons 1–4 on Prime, season 5 on Netflix" (issue #2).
 *
 * The title-level availability block answers for the whole show, which is wrong
 * for a show whose seasons moved service. This fills that gap — and only that
 * gap: when every season streams in the same place the block hides itself,
 * because the availability rows above already said so.
 *
 * A season counts as available as soon as a provider carries it, whether or not
 * every episode has aired — mid-release seasons are still watchable.
 */
export function SeasonAvailabilityBlock({ itemId, region }: { itemId: number; region: string }) {
  const q = useQuery({
    queryKey: ["season-availability", itemId, region],
    queryFn: () => api.seasonAvailability(itemId, region),
  });

  const data = q.data;
  if (!data || !data.split) return null;

  return (
    <div>
      <h2 className="mb-2 font-mono text-[0.75rem] tracking-widest text-muted">BY SEASON</h2>
      <div className="space-y-2">
        {data.groups.map((g) => (
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
              <span className="flex min-w-0 flex-wrap items-center justify-end gap-x-3 gap-y-1">
                {g.offers.map((o) => (
                  <ServiceMark key={o.service_key} name={o.service_name}
                               logo={o.logo} owned={o.owned} />
                ))}
              </span>
            ) : (
              <span className="font-mono text-[0.75rem] text-muted">not reported</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
