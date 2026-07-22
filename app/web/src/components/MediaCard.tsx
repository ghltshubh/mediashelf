import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import type { Badge, ShelfItem } from "../lib/api";
import { ServiceMark } from "./ServiceMark";

/** Group badges into distinct services, split by ownership. Badges arrive
    owned-first / streaming-first from the backend, so the first badge kept per
    service_key reflects that service's owned status. A service counts as owned
    if any of its offers is on one of your subscriptions. */
function serviceSummary(badges: Badge[]): { owned: Badge[]; others: Badge[] } {
  const byKey = new Map<string, Badge>();
  for (const b of badges) {
    if (!byKey.has(b.service_key)) byKey.set(b.service_key, b);
  }
  const distinct = [...byKey.values()];
  return {
    owned: distinct.filter((b) => b.owned),
    others: distinct.filter((b) => !b.owned),
  };
}

/** Poster card with the lit-shelf ownership treatment (Part 2 §4.2).
    `fluid` stretches to the grid cell (browse page) instead of rail width. */
export function MediaCard({ item, fluid = false }: { item: ShelfItem; fluid?: boolean }) {
  const { owned: ownedServices, others: otherServices } = serviceSummary(item.badges);

  // Where it actually streams. Owned items: your subscribed logo(s) that fit (up
  // to 3) + a "+N more" count. Non-owned: 2–3 logos so you can pick. This wins
  // over list_source everywhere — a watchlist card shows where to watch, not just
  // the list you added it from (which may differ from where it streams).
  let serviceMarks: ReactNode = null;
  if (item.owned) {
    const shownOwned = ownedServices.slice(0, 3);
    const moreCount = ownedServices.length - shownOwned.length + otherServices.length;
    serviceMarks = (
      <span className="flex min-w-0 items-center gap-1">
        {shownOwned.map((b) => (
          <ServiceMark key={b.service_key} name={b.service_name} logo={b.logo} owned />
        ))}
        {moreCount > 0 && (
          <span className="shrink-0 text-muted" title={`also on ${moreCount} other service${moreCount > 1 ? "s" : ""}`}>
            +{moreCount}
          </span>
        )}
      </span>
    );
  } else if (otherServices.length > 0) {
    serviceMarks = (
      <span className="flex min-w-0 items-center gap-1">
        {otherServices.slice(0, 3).map((b) => (
          <ServiceMark key={b.service_key} name={b.service_name} logo={b.logo} owned={false} />
        ))}
        {otherServices.length > 3 && (
          <span className="shrink-0 text-muted">+{otherServices.length - 3}</span>
        )}
      </span>
    );
  }
  return (
    <Link
      to={`/title/${item.id}`}
      className={`hoverable group relative rounded-[10px] bg-bg1 outline-offset-4 ${
        fluid ? "w-full" : "w-[148px] shrink-0 sm:w-[168px]"
      } ${item.owned ? "lit" : "dimmed"}`}
      aria-label={`${item.title}${item.year ? ` (${item.year})` : ""}${item.owned ? " — on your services" : ""}`}
    >
      <div className="relative aspect-[2/3] overflow-hidden rounded-[10px] bg-bg2">
        {item.poster ? (
          <img
            src={item.poster}
            alt={item.title}
            loading="lazy"
            className="poster h-full w-full object-cover"
          />
        ) : (
          <div className="flex h-full items-center justify-center p-3 text-center font-display text-sm text-muted">
            {item.title}
          </div>
        )}
        {/* Rating sits inside the poster, bottom-left, on a translucent chip —
            it stays over the image and never reaches the title row below. */}
        {item.rating ? (
          <span className="absolute bottom-1.5 left-1.5 rounded-full bg-bg0/35 px-1.5 py-0.5 font-mono text-[0.7rem] text-ink/90 backdrop-blur-[1px]">
            ★ {item.rating.toFixed(1)}
          </span>
        ) : null}
      </div>

      {item.badges.length === 0 && (
        <span className="absolute left-1.5 top-1.5 max-w-[calc(100%-12px)] truncate whitespace-nowrap rounded-full bg-bg0/85 px-2 py-0.5 font-mono text-[0.7rem] text-muted">
          not streaming yet
        </span>
      )}

      <div className="hoverable rounded-b-[10px] px-2 py-2 group-hover:bg-bg2 group-focus-visible:bg-bg2">
        <p className="truncate text-[0.875rem] leading-tight">{item.title}</p>
        <p className="mt-0.5 flex items-center justify-between gap-2 font-mono text-[0.75rem] text-muted">
          <span className="shrink-0">{item.year ?? "—"}</span>
          {serviceMarks ??
            (item.expected_service ? (
              // Upcoming, not streaming yet: studio-inferred likely home. A
              // prediction — dimmed and labelled so it never reads as confirmed.
              <span
                className="flex min-w-0 items-center gap-1 opacity-70"
                title={`expected on ${item.expected_service.service_name} · predicted from the studio, not confirmed`}
              >
                <span className="shrink-0 text-muted">expected</span>
                <ServiceMark
                  name={item.expected_service.service_name}
                  logo={item.expected_service.logo}
                  owned={false}
                />
              </span>
            ) : item.list_source ? (
              // Watchlist item that isn't streaming on any service yet: fall back
              // to the list you added it from ("on your Tubi list").
              <span className="flex min-w-0 items-center gap-1" title={`on your ${item.list_source} list`}>
                <ServiceMark name={item.list_source} logo={item.list_source_logo} owned={item.owned} />
              </span>
            ) : null)}
        </p>
      </div>
    </Link>
  );
}
