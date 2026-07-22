import { useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { DiscoveryCard } from "../components/DiscoveryCard";
import { EmptyState } from "../components/EmptyState";
import { api } from "../lib/api";

/** Person page (browse-by-actor/director): profile + filmography as cards. */
export function Person() {
  const { id } = useParams();
  const navigate = useNavigate();
  const query = useQuery({
    queryKey: ["person", id],
    queryFn: () => api.person(Number(id)),
    enabled: !!id,
  });

  if (query.isError) {
    return <EmptyState message="Couldn't load that person." />;
  }
  if (!query.data) {
    return (
      <div className="flex gap-6">
        <div className="h-40 w-28 animate-pulse rounded-[10px] bg-bg1" />
        <div className="flex-1 space-y-3 pt-2">
          <div className="h-7 w-1/3 animate-pulse rounded bg-bg1" />
          <div className="h-4 w-1/4 animate-pulse rounded bg-bg1" />
        </div>
      </div>
    );
  }

  const p = query.data;
  return (
    <div>
      <button
        onClick={() => navigate(-1)}
        className="hoverable mb-6 rounded-[6px] px-2 py-1 font-mono text-[0.8rem] text-muted hover:bg-bg2 hover:text-ink"
      >
        ← Back
      </button>

      <div className="flex flex-col gap-6 sm:flex-row">
        {p.profile ? (
          <img src={p.profile} alt="" className="h-40 w-28 shrink-0 rounded-[10px] object-cover" />
        ) : (
          <div className="flex h-40 w-28 shrink-0 items-center justify-center rounded-[10px] bg-bg2 text-[2rem] text-muted">
            {p.name.slice(0, 1)}
          </div>
        )}
        <div className="min-w-0 flex-1">
          <h1 className="font-display text-[2rem] font-bold leading-tight">{p.name}</h1>
          {p.known_for && <p className="mt-1 font-mono text-[0.8rem] text-muted">{p.known_for}</p>}
          {p.biography && (
            <p className="clamp-3 mt-3 max-w-2xl text-[0.9rem] text-ink/90">{p.biography}</p>
          )}
        </div>
      </div>

      <h2 className="mb-3 mt-8 font-mono text-[0.75rem] tracking-widest text-muted">
        FILMOGRAPHY · {p.credits.length}
      </h2>
      {p.credits.length === 0 ? (
        <p className="font-mono text-[0.8rem] text-muted">No movie or TV credits found.</p>
      ) : (
        <div className="grid grid-cols-3 gap-4 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6">
          {p.credits.map((c) => (
            <DiscoveryCard key={`${c.media_type}-${c.tmdb_id ?? c.id}`} item={c} />
          ))}
        </div>
      )}
    </div>
  );
}
