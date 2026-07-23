import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { DiscoveryCard } from "./DiscoveryCard";

/** Home rail: recommendations seeded by the newest watchlist title
    ("Because you saved X"). Quietly absent with no watchlist / no matches. */
export function BecauseRail() {
  const q = useQuery({ queryKey: ["because"], queryFn: api.because, staleTime: 30 * 60_000 });
  const data = q.data;
  if (!data?.seed || data.items.length === 0) return null;

  return (
    <section className="mb-10">
      <h2 className="mb-3 font-display text-[1.25rem] font-semibold">
        Because you saved{" "}
        <span className="text-owned">{data.seed}</span>
      </h2>
      <div className="flex gap-4 overflow-x-auto pb-2">
        {data.items.map((it) => (
          <div key={`${it.media_type}-${it.tmdb_id ?? it.id}`} className="w-[130px] shrink-0 sm:w-[150px]">
            <DiscoveryCard item={it} />
          </div>
        ))}
      </div>
    </section>
  );
}
