import type { ReactNode } from "react";
import type { Badge } from "../lib/api";
import { ServiceMark } from "./ServiceMark";

/** Group badges into distinct services, split by ownership. Badges arrive
    owned-first / streaming-first from the backend, so the first badge kept per
    service_key reflects that service's owned status. */
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

/** The bottom-of-card service logos. Owned items: your subscribed logo(s) that
    fit (up to 3) + a "+N" count; non-owned: 2–3 logos so you can pick where to
    watch. Returns null when there's nothing to show (so callers can fall back to
    an "expected on X" / list-source hint). Shared by MediaCard and DiscoveryCard. */
export function serviceMarksNode(badges: Badge[], owned: boolean): ReactNode | null {
  const { owned: ownedServices, others: otherServices } = serviceSummary(badges);
  if (owned) {
    const shown = ownedServices.slice(0, 3);
    const more = ownedServices.length - shown.length + otherServices.length;
    return (
      <span className="flex min-w-0 items-center gap-1">
        {shown.map((b) => (
          <ServiceMark key={b.service_key} name={b.service_name} logo={b.logo} owned />
        ))}
        {more > 0 && (
          <span
            className="shrink-0 text-muted"
            title={`also on ${more} other service${more > 1 ? "s" : ""}`}
          >
            +{more}
          </span>
        )}
      </span>
    );
  }
  if (otherServices.length > 0) {
    return (
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
  return null;
}
