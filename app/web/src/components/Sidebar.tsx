import { NavLink } from "react-router-dom";

const ITEMS = [
  { to: "/", glyph: "◆", label: "Shelf" },
  { to: "/search", glyph: "⌕", label: "Search" },
  { to: "/library", glyph: "▤", label: "Library" },
  { to: "/migrations", glyph: "⇄", label: "Migrations" },
  { to: "/settings", glyph: "⚙", label: "Settings" },
];

/** Left sidebar; icons-only under 1100px, bottom tab bar under 700px (Part 2 §3, §7). */
export function Sidebar() {
  return (
    <nav
      aria-label="Main"
      className="fixed inset-x-0 bottom-0 z-20 flex border-t border-line bg-bg1
                 min-[700px]:inset-x-auto min-[700px]:inset-y-0 min-[700px]:left-0 min-[700px]:w-[64px]
                 min-[700px]:flex-col min-[700px]:border-r min-[700px]:border-t-0 min-[700px]:pt-5
                 min-[1100px]:w-[200px]"
    >
      <div className="hidden px-4 pb-6 font-display text-[1.1rem] font-bold text-owned min-[1100px]:block">
        MediaShelf
      </div>
      {ITEMS.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.to === "/"}
          className={({ isActive }) =>
            `hoverable flex flex-1 items-center justify-center gap-3 px-3 py-3 text-[0.9rem]
             min-[700px]:flex-none min-[700px]:justify-center min-[1100px]:justify-start ${
               isActive ? "text-owned" : "text-muted hover:bg-bg2 hover:text-ink"
             }`
          }
        >
          <span aria-hidden className="text-[1.05rem]">{item.glyph}</span>
          <span className="hidden min-[1100px]:inline">{item.label}</span>
          <span className="sr-only min-[1100px]:hidden">{item.label}</span>
        </NavLink>
      ))}
    </nav>
  );
}
