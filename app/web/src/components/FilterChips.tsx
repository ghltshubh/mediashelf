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
          className={`hoverable rounded-full border px-3 py-1 text-[0.875rem] ${
            active === c.key
              ? "border-owned bg-owned/15 text-owned"
              : "border-line text-muted hover:bg-bg2"
          }`}
        >
          {c.label}
        </button>
      ))}
    </div>
  );
}
