import type { Badge as BadgeT } from "../lib/api";

const OFFER_LABEL: Record<string, string> = {
  flatrate: "",
  free: "free",
  ads: "ads",
  rent: "rent",
  buy: "buy",
};

/** Service pill — lit (owned) vs dimmed (elsewhere). Never color alone: text always present. */
export function Badge({ badge }: { badge: BadgeT }) {
  const offer = OFFER_LABEL[badge.offer_type];
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-mono text-[0.75rem] ${
        badge.owned
          ? "border-owned/50 bg-owned/10 text-owned"
          : "border-line text-muted"
      }`}
      title={badge.owned ? `${badge.service_name} — on your services` : `${badge.service_name} — not subscribed`}
    >
      {badge.service_name}
      {offer && <span className="opacity-70">· {offer}</span>}
    </span>
  );
}
