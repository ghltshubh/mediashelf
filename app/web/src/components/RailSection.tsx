import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ageOf, daysSince } from "../lib/time";

export function RailSection({
  label,
  railKey,
  total,
  shown,
  region,
  filter,
  mediaType,
  genre,
  updatedAt,
  children,
}: {
  label: string;
  railKey?: string;
  updatedAt?: string | null;
  total?: number;
  shown?: number;
  region?: string;
  filter?: string;
  mediaType?: string;
  genre?: string;
  children: ReactNode;
}) {
  const params = new URLSearchParams();
  if (region) params.set("region", region);
  if (filter && filter !== "all" && !railKey?.startsWith("svc_")) params.set("filter", filter);
  if (mediaType) params.set("type", mediaType);
  if (genre) params.set("genre", genre);
  const qs = params.toString();
  const to = railKey ? `/browse/${railKey}${qs ? `?${qs}` : ""}` : undefined;
  // Only offer "see all" when there's genuinely more than the rail shows.
  // A rail that already displays its whole set (Popular right now, Watchlist,
  // small categories) has nothing more to reveal, so it's a plain heading.
  const hasMore = total != null && shown != null && total > shown;
  // A week is long enough that a daily schedule has plainly missed several runs.
  const stale = (daysSince(updatedAt) ?? 0) > 7;
  const linkable = to != null && hasMore;
  return (
    <section className="mb-10">
      <div className="mb-3 flex items-baseline gap-3">
        {linkable ? (
          <Link
            to={to}
            className="group flex items-baseline gap-1.5 font-display text-[1.25rem] font-semibold hover:text-owned"
          >
            <span className="underline decoration-line decoration-1 underline-offset-4 group-hover:decoration-[var(--owned)]">
              {label}
            </span>
            <span aria-hidden className="text-[1rem] text-muted group-hover:text-owned">›</span>
          </Link>
        ) : (
          <h2 className="font-display text-[1.25rem] font-semibold">{label}</h2>
        )}
        {linkable && (
          <Link to={to} className="font-mono text-[0.75rem] text-muted hover:text-owned">
            see all {total} →
          </Link>
        )}
        {/* Imported lists only. These are filled from outside the app, so a
            clip that quietly stopped working leaves a healthy-looking rail
            serving old data — the age is what gives it away. Silent while
            it's fresh; nobody needs a timestamp on working data. */}
        {stale && (
          <span
            className="font-mono text-[0.72rem] text-muted"
            title={`Newest entry in this list is from ${updatedAt}`}
          >
            updated {ageOf(updatedAt)}
          </span>
        )}
      </div>
      <div className="rail flex gap-4 overflow-x-auto pb-4 pt-1">{children}</div>
    </section>
  );
}
