import type { VideoResult } from "../lib/api";
import { useActivate } from "../lib/searchData";

/** Poster card for discovery rows ("More like this", a person's filmography).
    Local titles link to their page; not-yet-imported ones import on click, both
    via the shared useActivate flow. Ownership drives the lit/dimmed treatment. */
export function DiscoveryCard({ item }: { item: VideoResult }) {
  const { activate, importing } = useActivate();
  const subtitle = item.role
    ? item.role
    : [item.year, item.owned ? "on your services" : null].filter(Boolean).join(" · ");
  return (
    <button
      onClick={() => void activate(item)}
      disabled={importing}
      title={item.title}
      className="block w-full cursor-pointer text-left disabled:cursor-default disabled:opacity-60"
    >
      <div className={`${item.owned ? "lit" : "dimmed"} overflow-hidden rounded-[10px]`}>
        {item.poster ? (
          <img
            src={item.poster}
            alt=""
            loading="lazy"
            className="poster aspect-[2/3] w-full object-cover"
          />
        ) : (
          <div className="flex aspect-[2/3] items-center justify-center rounded-[10px] bg-bg1 p-2 text-center font-display text-[0.8rem] text-muted">
            {item.title}
          </div>
        )}
      </div>
      <p className="mt-1.5 truncate text-[0.82rem] leading-tight">{item.title}</p>
      {subtitle && <p className="truncate font-mono text-[0.68rem] text-muted">{subtitle}</p>}
    </button>
  );
}
