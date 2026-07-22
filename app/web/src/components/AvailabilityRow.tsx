import type { Badge } from "../lib/api";
import { ageOf } from "../lib/time";

const OFFER_LABEL: Record<string, string> = {
  flatrate: "streaming",
  free: "free",
  ads: "free with ads",
  rent: "rent",
  buy: "buy",
};

/** One service row in the title page availability block (Part 2 §4.4). */
export function AvailabilityRow({ badge }: { badge: Badge }) {
  const checked = ageOf(badge.checked_at);
  return (
    <div
      title={checked ? `Availability last checked ${checked}` : undefined}
      className={`flex items-center justify-between gap-3 rounded-[6px] border px-3 py-2.5 ${
        badge.owned ? "border-owned/40 bg-owned/[0.07]" : "border-line bg-bg1"
      }`}
    >
      <div className="flex min-w-0 items-baseline gap-2">
        <span className={`truncate text-[0.95rem] ${badge.owned ? "text-ink" : "text-muted"}`}>
          {badge.service_name}
        </span>
        <span className="shrink-0 font-mono text-[0.75rem] text-muted">
          {OFFER_LABEL[badge.offer_type] ?? badge.offer_type}
          {badge.price ? ` · ${badge.price}` : ""}
        </span>
      </div>
      <div className="flex shrink-0 items-center gap-3 font-mono text-[0.8rem]">
        {badge.deep_link && (
          <a
            href={badge.deep_link}
            target="_blank"
            rel="noreferrer"
            className={`hoverable rounded-[6px] px-2 py-1 ${
              badge.owned ? "text-owned hover:bg-owned/15" : "text-muted hover:bg-bg2"
            }`}
          >
            ↗ Open
          </a>
        )}
        {!badge.owned && badge.signup_url && (
          <a
            href={badge.signup_url}
            target="_blank"
            rel="noreferrer"
            className="hoverable rounded-[6px] px-2 py-1 text-owned hover:bg-owned/15"
            title={badge.sso_note ? `Sign-in options: ${badge.sso_note}` : undefined}
          >
            + Get
          </a>
        )}
      </div>
    </div>
  );
}
