import type { Service } from "../lib/api";

/** Subscription checklist tile: dimmed (off) ↔ lit with glow (on) —
    teaches the lit-shelf language before the user sees the shelf.
    `action` adds a secondary setup link (connect / watchlist import) beneath
    the toggle, so setup is reachable right from the service. */
export function ServiceTile({
  service,
  onToggle,
  action,
}: {
  service: Service;
  onToggle: (subscribed: boolean) => void;
  action?: { label: string; href: string; external?: boolean; done?: boolean };
}) {
  const on = service.subscribed;
  return (
    <div
      className={`flex min-h-[64px] flex-col rounded-[10px] border px-3 py-2 ${
        on ? "lit border-owned/50 bg-owned/10" : "border-line bg-bg1 opacity-70 hover:opacity-100"
      }`}
    >
      <button
        onClick={() => onToggle(!on)}
        aria-pressed={on}
        className="flex flex-1 flex-col items-start justify-center text-left"
      >
        <span className={`font-display text-[0.95rem] font-semibold ${on ? "text-owned" : "text-ink"}`}>
          {service.name}
        </span>
        <span className="font-mono text-[0.7rem] text-muted">
          {service.kind}{on ? " · subscribed" : ""}
        </span>
        {service.featured && !service.custom && (
          <span className={`mt-0.5 font-mono text-[0.62rem] ${on ? "text-owned/80" : "text-muted/70"}`}>
            {service.integration}
          </span>
        )}
        {service.custom && (
          <span className="mt-0.5 font-mono text-[0.65rem] text-muted/80">
            your service · opens {hostOf(service.homepage_url)} · no availability data
          </span>
        )}
      </button>
      {action && (
        <a
          href={action.href}
          {...(action.external ? { target: "_blank", rel: "noreferrer" } : {})}
          onClick={(e) => e.stopPropagation()}
          className={`mt-1.5 self-start rounded-[6px] border px-2 py-0.5 font-mono text-[0.62rem] ${
            action.done
              ? "border-[color:var(--play)]/50 text-[color:var(--play)] hover:bg-[color:var(--play)]/10"
              : "border-line text-owned hover:bg-owned/10"
          }`}
        >
          {action.done ? "✓" : "↗"} {action.label}
        </a>
      )}
    </div>
  );
}

function hostOf(url: string | null): string {
  if (!url) return "homepage";
  try {
    return new URL(url).host;
  } catch {
    return "homepage";
  }
}
