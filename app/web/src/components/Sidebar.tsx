import { Link, NavLink } from "react-router-dom";
import { useT } from "../lib/i18n";
import { Logo } from "./Logo";

const ITEMS = [
  { to: "/", glyph: "◆", key: "nav.shelf" },
  { to: "/search", glyph: "⌕", key: "nav.search" },
  { to: "/library", glyph: "▤", key: "nav.library" },
  { to: "/migrations", glyph: "⇄", key: "nav.migrations" },
  { to: "/settings", glyph: "⚙", key: "nav.settings" },
];

/** Left sidebar; icons-only under 1100px, bottom tab bar under 700px (Part 2 §3, §7). */
export function Sidebar() {
  const t = useT();
  return (
    <nav
      aria-label="Main"
      className="fixed inset-x-0 bottom-0 z-20 flex border-t border-line bg-bg1
                 min-[700px]:inset-x-auto min-[700px]:inset-y-0 min-[700px]:left-0 min-[700px]:w-[64px]
                 min-[700px]:flex-col min-[700px]:border-r min-[700px]:border-t-0 min-[700px]:pt-5
                 min-[1100px]:w-[200px]"
    >
      {/* Brand: mark + wordmark on the wide rail, mark-only on the icon rail.
          Links home. */}
      <Link
        to="/"
        aria-label="MediaShelf — home"
        className="hoverable hidden items-center gap-2 rounded-[8px] px-4 pb-6 min-[700px]:flex min-[700px]:justify-center min-[1100px]:justify-start"
      >
        <Logo className="h-7 w-7 shrink-0" />
        <span className="hidden font-display text-[1.15rem] font-bold tracking-tight text-owned min-[1100px]:inline">
          MediaShelf
        </span>
      </Link>
      {ITEMS.map((item) => {
        const label = t(item.key);
        return (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            className={({ isActive }) =>
              `hoverable flex flex-1 items-center justify-center gap-3 px-3 py-3 font-display
               text-[0.95rem] font-medium tracking-tight
               min-[700px]:flex-none min-[700px]:justify-center min-[1100px]:justify-start ${
                 isActive ? "text-owned" : "text-muted hover:bg-bg2 hover:text-ink"
               }`
            }
          >
            <span aria-hidden className="text-[1.05rem]">{item.glyph}</span>
            <span className="hidden min-[1100px]:inline">{label}</span>
            <span className="sr-only min-[1100px]:hidden">{label}</span>
          </NavLink>
        );
      })}
    </nav>
  );
}
