import type { Badge } from "../lib/api";

/** Small service mark: logo when available, else a short name slice. Owned
    services get a faint brass ring so the ownership signal survives on logos.
    Shared by the shelf cards and the search palette. */
export function ServiceMark({
  name,
  logo,
  owned,
}: {
  name: string;
  logo?: string | null;
  owned: boolean;
}) {
  if (logo) {
    return (
      <img
        src={logo}
        alt={name}
        title={name}
        className={`h-4 w-4 shrink-0 rounded-[3px] object-contain ${owned ? "ring-1 ring-owned/60" : ""}`}
      />
    );
  }
  return (
    <span title={name} className={`shrink-0 ${owned ? "text-owned" : "text-muted"}`}>
      {name.slice(0, 3)}
    </span>
  );
}

/** Distinct services from a badge list, first occurrence wins (badges arrive
    owned-first / streaming-first from the backend). */
export function distinctServices(badges: Badge[], n = 4): Badge[] {
  const seen = new Set<string>();
  const out: Badge[] = [];
  for (const b of badges) {
    if (seen.has(b.service_key)) continue;
    seen.add(b.service_key);
    out.push(b);
    if (out.length >= n) break;
  }
  return out;
}
