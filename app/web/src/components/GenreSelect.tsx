/** Genre filter: scope the shelf to one genre. "" = all genres. Compact select
    so it sits alongside the sort/region controls without crowding the header. */
export function GenreSelect({
  value,
  genres,
  onChange,
}: {
  value: string;
  genres: string[];
  onChange: (v: string) => void;
}) {
  if (genres.length === 0) return null;
  return (
    <label className="flex items-center gap-1.5">
      <span className="font-mono text-[0.7rem] text-muted">genre</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-label="Filter by genre"
        className="rounded-[6px] border border-line bg-bg1 px-2 py-1 font-mono text-[0.75rem] text-ink outline-none focus:border-owned/60"
      >
        <option value="">All genres</option>
        {genres.map((g) => (
          <option key={g} value={g}>{g}</option>
        ))}
      </select>
    </label>
  );
}
