import { Link } from "react-router-dom";
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
        {service.custom && (
          <span className="mt-0.5 font-mono text-[0.65rem] text-muted/80">
            your service · opens {hostOf(service.homepage_url)} · no availability data
          </span>
        )}
      </button>
      {/* A text link, deliberately not a button: a bordered pill inside the
          glowing tile read as a button-in-a-button, with no hint that the tile
          toggles while the pill navigates. Underline = goes somewhere. */}
      {action && (() => {
        const cls = `mt-1 self-start font-mono text-[0.65rem] underline decoration-dotted underline-offset-2 hover:decoration-solid ${
          action.done ? "text-[color:var(--play)]" : "text-owned"
        }`;
        const body = <>{action.done ? "✓" : "↗"} {action.label}</>;
        // In-app routes go through the router (no full reload); hashes and
        // external tools stay plain anchors.
        return !action.external && action.href.startsWith("/") ? (
          <Link to={action.href} onClick={(e) => e.stopPropagation()} className={cls}>
            {body}
          </Link>
        ) : (
          <a
            href={action.href}
            {...(action.external ? { target: "_blank", rel: "noreferrer" } : {})}
            onClick={(e) => e.stopPropagation()}
            className={cls}
          >
            {body}
          </a>
        );
      })()}
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
