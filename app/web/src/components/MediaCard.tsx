import { Link } from "react-router-dom";
import type { ShelfItem } from "../lib/api";
import { ServiceMark } from "./ServiceMark";
import { serviceMarksNode } from "./serviceMarks";

/** Poster card with the lit-shelf ownership treatment (Part 2 §4.2).
    `fluid` stretches to the grid cell (browse page) instead of rail width. */
export function MediaCard({ item, fluid = false }: { item: ShelfItem; fluid?: boolean }) {
  // Where it actually streams — owned logo(s) + "+N", or 2–3 options if not owned.
  // Wins over list_source everywhere (a watchlist card shows where to watch).
  const serviceMarks = serviceMarksNode(item.badges, item.owned);
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
        // Not streaming yet: a quiet semi-transparent mark instead of a repeated
        // text banner (a row of upcoming titles would otherwise shout in unison).
        // The "expected on X" hint below still names the likely home.
        <span
          title="not streaming yet"
          aria-label="not streaming yet"
          className="absolute left-1.5 top-1.5 text-[1.05rem] leading-none opacity-50 drop-shadow-[0_1px_2px_rgba(0,0,0,0.75)]"
        >
          🚫
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
