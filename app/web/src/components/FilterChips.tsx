export interface Chip {
  key: string;
  label: string;
}

export function FilterChips({
  chips,
  active,
  onSelect,
}: {
  chips: Chip[];
  active: string;
  onSelect: (key: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2" role="group" aria-label="Filter titles">
      {chips.map((c) => (
        <button
          key={c.key}
          onClick={() => onSelect(c.key)}
          aria-pressed={active === c.key}
          className={`hoverable rounded-[6px] border px-3 py-1 font-mono text-[0.75rem] ${
            active === c.key
              ? "border-owned/60 bg-owned/15 text-owned"
              : "border-line text-muted hover:bg-bg2"
          }`}
        >
          {c.label}
        </button>
      ))}
    </div>
  );
}
