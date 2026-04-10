import { useState } from "react";
import Sidebar from "./Sidebar";
import SitesList from "./SitesList";
import SiteDetail from "./SiteDetail";
import Settings from "./Settings";
import Help from "./Help";

export type View =
  | { name: "sites" }
  | { name: "site"; site: string }
  | { name: "settings" }
  | { name: "help" };

export default function App() {
  const [view, setView] = useState<View>({ name: "sites" });

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: "var(--color-navy)", color: "#e6edf3" }}>
      <Sidebar view={view} navigate={setView} />
      <main className="flex-1 overflow-auto">
        {view.name === "sites" && <SitesList navigate={setView} />}
        {view.name === "site" && <SiteDetail site={view.site} navigate={setView} />}
        {view.name === "settings" && <Settings />}
        {view.name === "help" && <Help />}
      </main>
    </div>
  );
}
