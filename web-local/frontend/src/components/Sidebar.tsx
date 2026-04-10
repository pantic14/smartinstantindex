import type { View } from "./App";

interface Props {
  view: View;
  navigate: (v: View) => void;
}

const NAV = [
  { name: "sites" as const, label: "Sites" },
  { name: "settings" as const, label: "Settings" },
  { name: "help" as const, label: "Help" },
];

export default function Sidebar({ view, navigate }: Props) {
  const active = view.name === "site" ? "sites" : view.name;

  return (
    <aside
      className="flex flex-col w-52 shrink-0 border-r"
      style={{ background: "var(--color-navy-mid)", borderColor: "var(--color-rim)" }}
    >
      {/* Logo */}
      <div className="px-4 py-4 border-b" style={{ borderColor: "var(--color-rim)" }}>
        <div className="flex items-center gap-2.5">
          <img src="/android-chrome-192x192.png" alt="SmartInstantIndex" className="w-7 h-7 rounded-md shrink-0" />
          <span className="font-semibold text-sm">SmartInstantIndex</span>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-2 py-3 space-y-0.5 text-sm">
        {NAV.map((item) => {
          const isActive = active === item.name;
          return (
            <button
              key={item.name}
              onClick={() => navigate({ name: item.name })}
              className="w-full text-left px-3 py-2 rounded-lg transition-colors"
              style={{
                background: isActive ? "var(--color-accent-dim)" : "transparent",
                color: isActive ? "var(--color-accent-hover)" : "var(--color-muted)",
                fontWeight: isActive ? 500 : 400,
              }}
              onMouseEnter={(e) => {
                if (!isActive) (e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,0.05)";
              }}
              onMouseLeave={(e) => {
                if (!isActive) (e.currentTarget as HTMLElement).style.background = "transparent";
              }}
            >
              {item.label}
            </button>
          );
        })}
      </nav>

      <div className="px-4 py-3 border-t text-xs" style={{ borderColor: "var(--color-rim)", color: "var(--color-muted)" }}>
        local
      </div>
    </aside>
  );
}
