import { AvailabilityRow } from "../components/AvailabilityRow";
import { Badge } from "../components/Badge";
import { EmptyState } from "../components/EmptyState";
import { FilterChips } from "../components/FilterChips";
import { KeyValueMono } from "../components/KeyValueMono";
import { MediaCard } from "../components/MediaCard";
import { StatusBanner } from "../components/StatusBanner";
import type { Badge as BadgeT, ShelfItem } from "../lib/api";

const owned: BadgeT = {
  service_key: "netflix", service_name: "Netflix", logo: null, offer_type: "flatrate", owned: true,
  deep_link: "#", price: null, signup_url: null, sso_note: null, plan_price: null,
  checked_at: new Date(Date.now() - 3600e3).toISOString(),
};
const elsewhere: BadgeT = { ...owned, service_key: "max", service_name: "Max", owned: false, signup_url: "#" };

const item: ShelfItem = {
  id: 0, media_type: "movie", title: "Demo Title", year: 2024, poster: null, backdrop: null,
  rating: 7.7, genres: ["Drama"], owned: true, unlock_service: null, badges: [owned, elsewhere],
};

/** Component demo page — debug builds only (Part 2 §5). */
export function DevComponents() {
  return (
    <div className="max-w-2xl space-y-10">
      <h1 className="font-display text-[1.6rem] font-bold">/dev/components</h1>
      <section><h2 className="mb-3 font-mono text-[0.75rem] text-muted">MEDIACARD (lit / dimmed)</h2>
        <div className="flex gap-4">
          <MediaCard item={item} />
          <MediaCard item={{ ...item, id: 1, owned: false, unlock_service: "Max" }} />
        </div>
      </section>
      <section><h2 className="mb-3 font-mono text-[0.75rem] text-muted">BADGE</h2>
        <div className="flex gap-2"><Badge badge={owned} /><Badge badge={elsewhere} /></div>
      </section>
      <section><h2 className="mb-3 font-mono text-[0.75rem] text-muted">AVAILABILITYROW</h2>
        <div className="space-y-2"><AvailabilityRow badge={owned} /><AvailabilityRow badge={elsewhere} /></div>
      </section>
      <section><h2 className="mb-3 font-mono text-[0.75rem] text-muted">FILTERCHIPS</h2>
        <FilterChips chips={[{ key: "all", label: "All" }, { key: "mine", label: "On my services" }]}
                     active="mine" onSelect={() => {}} />
      </section>
      <section><h2 className="mb-3 font-mono text-[0.75rem] text-muted">STATUSBANNER</h2>
        <StatusBanner kind="info">Catalog last updated 3 days ago.</StatusBanner>
        <StatusBanner kind="quota">Daily YouTube limit reached. Saved at 173/230; resumes tomorrow.</StatusBanner>
        <StatusBanner kind="danger">TMDB rejected the key: Invalid API key</StatusBanner>
      </section>
      <section><h2 className="mb-3 font-mono text-[0.75rem] text-muted">EMPTYSTATE</h2>
        <EmptyState message="Add your TMDB key to load the catalog." />
      </section>
      <section><h2 className="mb-3 font-mono text-[0.75rem] text-muted">KEYVALUEMONO</h2>
        <KeyValueMono pairs={[["TMDB key", "abcd…wxyz"], ["Country", "US"]]} />
      </section>
    </div>
  );
}
