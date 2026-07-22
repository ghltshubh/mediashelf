import type { VideoResult } from "../lib/api";
import { useActivate } from "../lib/searchData";
import { serviceMarksNode } from "./serviceMarks";

/** Poster card for discovery rows ("More like this", a person's filmography).
    Local titles link to their page; not-yet-imported ones import on click, both
    via the shared useActivate flow. Ownership drives the lit/dimmed treatment,
    and in-catalog titles show the same service logos as the shelf cards. */
export function DiscoveryCard({ item }: { item: VideoResult }) {
  const { activate, importing } = useActivate();
  const marks = serviceMarksNode(item.badges, item.owned);
  // Left of the meta row: the person-page role (character/job) if present, else year.
  const lead = item.role ?? (item.year != null ? String(item.year) : "—");
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
      <p className="mt-0.5 flex items-center justify-between gap-2 font-mono text-[0.68rem] text-muted">
        <span className="min-w-0 truncate">{lead}</span>
        {marks}
      </p>
    </button>
  );
}
