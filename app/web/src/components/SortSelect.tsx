/** Sort control for catalog rails / browse grid: Popular · A→Z · Newest.
    A compact select so it never crowds the header on mobile. */
export function SortSelect({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="flex items-center gap-1.5">
      <span className="font-mono text-[0.7rem] text-muted">sort</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-label="Sort titles"
        className="rounded-[6px] border border-line bg-bg1 px-2 py-1 font-mono text-[0.75rem] text-ink outline-none focus:border-owned/60"
      >
        <option value="popularity">Popular</option>
        <option value="title">A→Z</option>
        <option value="year">Newest</option>
      </select>
    </label>
  );
}
