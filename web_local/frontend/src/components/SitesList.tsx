import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { View } from "./App";
import SiteForm from "./SiteForm";

interface Site {
  name: string;
  sitemap_url: string;
  urls_total: number;
  urls_indexed: number;
  urls_pending: number;
}

interface Props {
  navigate: (v: View) => void;
}

export default function SitesList({ navigate }: Props) {
  const [sites, setSites] = useState<Site[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);

  async function load() {
    setLoading(true);
    try {
      setSites(await api.getSites());
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function handleDelete(e: React.MouseEvent, name: string) {
    e.stopPropagation();
    if (!confirm(`Delete site "${name}"?`)) return;
    await api.deleteSite(name);
    load();
  }

  if (loading) return (
    <div className="flex items-center justify-center h-full text-sm" style={{ color: "var(--color-muted)" }}>
      Loading…
    </div>
  );

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold">Sites</h1>
        <button
          onClick={() => setShowForm(true)}
          className="px-4 py-2 rounded-lg text-sm font-medium"
          style={{ background: "var(--color-accent)", color: "#fff" }}
          onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.background = "var(--color-accent-hover)")}
          onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.background = "var(--color-accent)")}
        >
          + New site
        </button>
      </div>

      {sites.length === 0 ? (
        <div
          className="border-2 border-dashed rounded-xl p-16 text-center"
          style={{ borderColor: "var(--color-rim)", color: "var(--color-muted)" }}
        >
          <p className="text-base mb-1">No sites yet</p>
          <p className="text-sm">Add your first site to start indexing.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {sites.map((site) => (
            <div
              key={site.name}
              onClick={() => navigate({ name: "site", site: site.name })}
              className="flex items-center justify-between gap-4 rounded-xl border px-5 py-4 cursor-pointer transition-colors"
              style={{ background: "var(--color-navy-card)", borderColor: "var(--color-rim)" }}
              onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.borderColor = "var(--color-accent)")}
              onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.borderColor = "var(--color-rim)")}
            >
              <div className="min-w-0">
                <p className="font-medium truncate">{site.name}</p>
                <p className="text-xs mt-0.5 truncate" style={{ color: "var(--color-muted)" }}>
                  {site.sitemap_url}
                </p>
                <div className="flex gap-4 mt-2 text-sm">
                  <span style={{ color: "var(--color-muted)" }}>{site.urls_total} URLs</span>
                  <span style={{ color: "var(--color-success)" }}>{site.urls_indexed} sent</span>
                  <span style={{ color: site.urls_pending > 0 ? "var(--color-warn)" : "var(--color-muted)" }}>
                    {site.urls_pending} pending
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <button
                  onClick={(e) => handleDelete(e, site.name)}
                  className="px-3 py-1.5 rounded-lg text-xs border transition-colors"
                  style={{ borderColor: "var(--color-rim)", color: "var(--color-muted)" }}
                  onMouseEnter={(e) => {
                    (e.currentTarget as HTMLElement).style.borderColor = "var(--color-danger)";
                    (e.currentTarget as HTMLElement).style.color = "var(--color-danger)";
                  }}
                  onMouseLeave={(e) => {
                    (e.currentTarget as HTMLElement).style.borderColor = "var(--color-rim)";
                    (e.currentTarget as HTMLElement).style.color = "var(--color-muted)";
                  }}
                >
                  Delete
                </button>
                <span style={{ color: "var(--color-muted)" }}>→</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {showForm && (
        <SiteForm
          site={null}
          onClose={() => setShowForm(false)}
          onSaved={() => { setShowForm(false); load(); }}
        />
      )}
    </div>
  );
}
