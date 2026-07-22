const regionNames = new Intl.DisplayNames(["en"], { type: "region" });

export function countryName(code: string): string {
  if (code === "ALL") return "All regions";
  try {
    return regionNames.of(code) ?? code;
  } catch {
    return code;
  }
}

/** Region switcher: chips while compact, a dropdown once the list would
    crowd the bar (someone tracking 50 countries gets a select, not 50 chips). */
export function RegionSwitcher({
  regions,
  active,
  onSelect,
}: {
  regions: string[];
  active: string;
  onSelect: (r: string) => void;
}) {
  if (regions.length <= 1) return null;
  // "ALL" aggregates every tracked region (labeled badges, owned-anywhere).
  const options = ["ALL", ...regions];
  if (regions.length > 4) {
    return (
      <select
        value={active}
        onChange={(e) => onSelect(e.target.value)}
        aria-label="Region"
        className="max-w-52 rounded-[6px] border border-line bg-bg1 px-2 py-1 font-mono text-[0.75rem] text-owned"
      >
        {options.map((r) => (
          <option key={r} value={r}>{countryName(r)}</option>
        ))}
      </select>
    );
  }
  return (
    <div role="group" aria-label="Region" className="flex rounded-[6px] border border-line">
      {options.map((r) => (
        <button
          key={r}
          onClick={() => onSelect(r)}
          aria-pressed={active === r}
          title={countryName(r)}
          className={`px-3 py-1 font-mono text-[0.75rem] first:rounded-l-[5px] last:rounded-r-[5px] ${
            active === r ? "bg-owned/15 text-owned" : "text-muted hover:bg-bg2"
          }`}
        >
          {r === "ALL" ? "All" : r}
        </button>
      ))}
    </div>
  );
}
