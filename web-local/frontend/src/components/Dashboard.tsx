import { useState, useEffect, useRef } from "react";
import { api } from "../lib/api";
import type { View } from "./App";
import SiteForm from "./SiteForm";

interface Props {
  navigate: (v: View) => void;
}

interface QuotaEntry {
  credentials_file: string;
  credentials_name: string;
  used: number;
  limit: number;
  remaining: number;
}

interface Site {
  name: string;
  sitemap_url: string;
  site_url: string;
  urls_total: number;
  urls_indexed: number;
  urls_pending: number;
  quota: QuotaEntry[];
  credentials: string[];
}

interface LogLine {
  type: string;
  message?: string;
  url?: string;
  done?: number;
  total?: number;
  count?: number;
  pending?: number;
  capacity?: number;
  indexed?: number;
}

export default function Dashboard({ navigate }: Props) {
  const [sites, setSites] = useState<Site[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [editSite, setEditSite] = useState<Site | null>(null);

  // Per-site run state
  const [running, setRunning] = useState<Record<string, boolean>>({});
  const [logs, setLogs] = useState<Record<string, LogLine[]>>({});
  const esSources = useRef<Record<string, EventSource>>({});

  async function load() {
    try {
      const data = await api.getSites();
      setSites(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    return () => {
      Object.values(esSources.current).forEach((es) => es.close());
    };
  }, []);

  async function handleDelete(name: string) {
    if (!confirm(`Delete site "${name}"?`)) return;
    await api.deleteSite(name);
    load();
  }

  function startRun(name: string) {
    if (esSources.current[name]) {
      esSources.current[name].close();
    }
    setRunning((r) => ({ ...r, [name]: true }));
    setLogs((l) => ({ ...l, [name]: [] }));

    const es = new EventSource(api.runStreamUrl(name));
    esSources.current[name] = es;

    es.onmessage = (e) => {
      const event: LogLine = JSON.parse(e.data);
      setLogs((l) => ({ ...l, [name]: [...(l[name] || []), event] }));
      if (event.type === "done" || event.type === "error") {
        es.close();
        setRunning((r) => ({ ...r, [name]: false }));
        load();
      }
    };

    es.onerror = () => {
      es.close();
      setRunning((r) => ({ ...r, [name]: false }));
      setLogs((l) => ({
        ...l,
        [name]: [...(l[name] || []), { type: "error", message: "Connection lost" }],
      }));
    };
  }

  function stopRun(name: string) {
    esSources.current[name]?.close();
    setRunning((r) => ({ ...r, [name]: false }));
  }

  function logSummary(name: string): string {
    const lines = logs[name] || [];
    const last = lines[lines.length - 1];
    if (!last) return "";
    if (last.type === "done")
      return `Done: ${last.indexed} indexed, ${last.pending} pending`;
    if (last.type === "indexed") return `Indexing… ${last.done}/${last.total}`;
    if (last.type === "quota_exhausted") return "Quota exhausted";
    if (last.type === "error") return `Error: ${last.message}`;
    if (last.type === "status") return last.message || "";
    if (last.type === "plan")
      return `Plan: ${last.pending} pending, ${last.capacity} capacity`;
    return last.type;
  }

  if (loading)
    return (
      <div className="flex items-center justify-center h-full" style={{ color: "var(--color-muted)" }}>
        Loading…
      </div>
    );

  if (error)
    return (
      <div className="p-8">
        <p style={{ color: "var(--color-danger)" }}>{error}</p>
        <button
          onClick={load}
          className="mt-2 text-sm underline"
          style={{ color: "var(--color-accent)" }}
        >
          Retry
        </button>
      </div>
    );

  return (
    <div className="p-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold">Sites</h1>
        <button
          onClick={() => { setEditSite(null); setShowForm(true); }}
          className="px-4 py-2 rounded-md text-sm font-medium transition-colors"
          style={{ background: "var(--color-accent)", color: "#fff" }}
          onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.background = "var(--color-accent-hover)")}
          onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.background = "var(--color-accent)")}
        >
          + New site
        </button>
      </div>

      {sites.length === 0 && (
        <div
          className="border border-dashed rounded-xl p-12 text-center"
          style={{ borderColor: "var(--color-rim)", color: "var(--color-muted)" }}
        >
          <p className="text-lg mb-1">No sites yet</p>
          <p className="text-sm">Add a site to start indexing.</p>
        </div>
      )}

      <div className="space-y-4">
        {sites.map((site) => {
          const isRunning = running[site.name];
          const siteLogs = logs[site.name] || [];
          const progress =
            siteLogs.find((l) => l.type === "indexed");
          const totalQuotaRemaining = site.quota.reduce(
            (sum, q) => sum + q.remaining,
            0
          );

          return (
            <div
              key={site.name}
              className="rounded-xl border p-5"
              style={{
                background: "var(--color-navy-card)",
                borderColor: "var(--color-rim)",
              }}
            >
              {/* Site header */}
              <div className="flex items-start justify-between gap-4 mb-4">
                <div className="min-w-0">
                  <h2 className="font-semibold text-base truncate">{site.name}</h2>
                  <a
                    href={site.sitemap_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs truncate block"
                    style={{ color: "var(--color-muted)" }}
                  >
                    {site.sitemap_url}
                  </a>
                </div>
                <div className="flex gap-2 shrink-0">
                  <button
                    onClick={() => navigate({ name: "urls", site: site.name })}
                    className="px-3 py-1.5 rounded-md text-xs border transition-colors"
                    style={{ borderColor: "var(--color-rim)", color: "var(--color-muted)" }}
                    onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.color = "#e6edf3")}
                    onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.color = "var(--color-muted)")}
                  >
                    URLs
                  </button>
                  <button
                    onClick={() => { setEditSite(site); setShowForm(true); }}
                    className="px-3 py-1.5 rounded-md text-xs border transition-colors"
                    style={{ borderColor: "var(--color-rim)", color: "var(--color-muted)" }}
                    onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.color = "#e6edf3")}
                    onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.color = "var(--color-muted)")}
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => handleDelete(site.name)}
                    className="px-3 py-1.5 rounded-md text-xs border transition-colors"
                    style={{ borderColor: "var(--color-rim)", color: "var(--color-danger)" }}
                    onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.borderColor = "var(--color-danger)")}
                    onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.borderColor = "var(--color-rim)")}
                  >
                    Delete
                  </button>
                </div>
              </div>

              {/* Stats row */}
              <div className="grid grid-cols-4 gap-3 mb-4">
                <Stat label="Total URLs" value={site.urls_total} />
                <Stat label="Indexed" value={site.urls_indexed} color="var(--color-success)" />
                <Stat label="Pending" value={site.urls_pending} color={site.urls_pending > 0 ? "var(--color-warn)" : undefined} />
                <Stat label="Quota left" value={totalQuotaRemaining} color={totalQuotaRemaining === 0 ? "var(--color-danger)" : undefined} />
              </div>

              {/* Quota details */}
              {site.quota.length > 0 && (
                <div className="flex flex-wrap gap-2 mb-4">
                  {site.quota.map((q) => (
                    <div
                      key={q.credentials_file}
                      className="px-2 py-1 rounded text-xs flex gap-2 items-center"
                      style={{ background: "rgba(255,255,255,0.04)", color: "var(--color-muted)" }}
                    >
                      <span className="font-mono truncate max-w-32">{q.credentials_name}</span>
                      <span
                        style={{
                          color:
                            q.remaining === 0
                              ? "var(--color-danger)"
                              : q.remaining < 50
                              ? "var(--color-warn)"
                              : "var(--color-success)",
                        }}
                      >
                        {q.remaining}/{q.limit}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {/* Run button + log */}
              <div className="flex items-center gap-3">
                {isRunning ? (
                  <button
                    onClick={() => stopRun(site.name)}
                    className="px-4 py-2 rounded-md text-sm font-medium border"
                    style={{ borderColor: "var(--color-danger)", color: "var(--color-danger)" }}
                  >
                    Stop
                  </button>
                ) : (
                  <button
                    onClick={() => startRun(site.name)}
                    disabled={site.credentials.length === 0}
                    className="px-4 py-2 rounded-md text-sm font-medium transition-colors disabled:opacity-40"
                    style={{ background: "var(--color-accent)", color: "#fff" }}
                    onMouseEnter={(e) => {
                      if (site.credentials.length > 0)
                        (e.currentTarget as HTMLElement).style.background = "var(--color-accent-hover)";
                    }}
                    onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.background = "var(--color-accent)")}
                    title={site.credentials.length === 0 ? "No credentials configured" : ""}
                  >
                    ▶ Run Indexing
                  </button>
                )}
                {siteLogs.length > 0 && (
                  <span className="text-xs" style={{ color: "var(--color-muted)" }}>
                    {logSummary(site.name)}
                  </span>
                )}
              </div>

              {/* SSE log lines */}
              {siteLogs.length > 0 && (
                <LogPanel lines={siteLogs} />
              )}
            </div>
          );
        })}
      </div>

      {/* Site form modal */}
      {showForm && (
        <SiteForm
          site={editSite}
          onClose={() => { setShowForm(false); setEditSite(null); }}
          onSaved={() => { setShowForm(false); setEditSite(null); load(); }}
        />
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color?: string;
}) {
  return (
    <div
      className="rounded-lg p-3"
      style={{ background: "rgba(255,255,255,0.03)", border: "1px solid var(--color-rim)" }}
    >
      <div className="text-xs mb-1" style={{ color: "var(--color-muted)" }}>
        {label}
      </div>
      <div className="text-xl font-semibold font-mono" style={{ color: color || "#e6edf3" }}>
        {value}
      </div>
    </div>
  );
}

function LogPanel({ lines }: { lines: LogLine[] }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [lines]);

  return (
    <div
      ref={ref}
      className="mt-3 rounded-md p-3 text-xs font-mono overflow-y-auto max-h-32 space-y-0.5"
      style={{ background: "rgba(0,0,0,0.3)", border: "1px solid var(--color-rim)" }}
    >
      {lines.map((l, i) => (
        <div
          key={i}
          style={{
            color:
              l.type === "error"
                ? "var(--color-danger)"
                : l.type === "quota_exhausted"
                ? "var(--color-warn)"
                : l.type === "indexed"
                ? "var(--color-success)"
                : l.type === "done"
                ? "var(--color-success)"
                : "var(--color-muted)",
          }}
        >
          {l.type === "indexed"
            ? `[${l.done}/${l.total}] ${l.url}`
            : l.type === "done"
            ? `✓ Done — indexed: ${l.indexed}, pending: ${l.pending}`
            : l.type === "plan"
            ? `Plan: ${l.pending} pending, ${l.capacity} capacity`
            : l.type === "urls_found"
            ? `Found ${l.count} URLs in sitemap`
            : l.message || l.type}
        </div>
      ))}
    </div>
  );
}
