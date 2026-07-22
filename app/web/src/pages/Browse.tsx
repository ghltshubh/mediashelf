import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { EmptyState } from "../components/EmptyState";
import { MediaCard } from "../components/MediaCard";
import { RegionSwitcher } from "../components/RegionSwitcher";
import { SortSelect } from "../components/SortSelect";
import { api } from "../lib/api";

/** "See all" page: the full contents of one shelf rail as a wrapping grid. */
export function Browse() {
  const { railKey } = useParams();
  const [params, setParams] = useSearchParams();
  const region = params.get("region") ?? "";
  const filter = params.get("filter") ?? "all";
  const type = params.get("type") ?? "";
  const genre = params.get("genre") ?? "";
  const [sort, setSort] = useState("popularity");
  const navigate = useNavigate();
  const query = useQuery({
    queryKey: ["rail", railKey, region, filter, type, sort, genre],
    queryFn: () => api.rail(railKey!, region, filter, type, sort, genre),
    enabled: !!railKey,
  });

  if (query.isError) return <EmptyState message="That rail doesn't exist anymore." />;
  if (!query.data) {
    return (
      <div className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-4">
        {Array.from({ length: 12 }).map((_, i) => (
          <div key={i} className="aspect-[2/3] animate-pulse rounded-[10px] bg-bg1" />
        ))}
      </div>
    );
  }

  const rail = query.data;
  return (
    <div>
      <button
        onClick={() => navigate(-1)}
        className="hoverable mb-4 rounded-[6px] px-2 py-1 font-mono text-[0.8rem] text-muted hover:bg-bg2 hover:text-ink"
      >
        ← Back
      </button>
      <div className="mb-6 flex flex-wrap items-center gap-4">
        <h1 className="font-display text-[1.6rem] font-bold">{rail.label}</h1>
        <span className="font-mono text-[0.8rem] text-muted">{rail.items.length} titles</span>
        <SortSelect value={sort} onChange={setSort} />
        {filter !== "all" && (
          <span className="rounded-full border border-owned/50 px-2 py-0.5 font-mono text-[0.7rem] text-owned">
            {filter === "mine" ? "on my services" : filter === "elsewhere" ? "not on my services" : filter}
          </span>
        )}
        <RegionSwitcher
          regions={rail.regions}
          active={rail.country}
          onSelect={(r) => {
            const next: Record<string, string> = { region: r };
            if (filter !== "all") next.filter = filter;
            if (type) next.type = type;
            setParams(next, { replace: true });
          }}
        />
      </div>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-4">
        {rail.items.map((item) => (
          <MediaCard key={item.id} item={item} fluid />
        ))}
      </div>
    </div>
  );
}
