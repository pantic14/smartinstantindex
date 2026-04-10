import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import type { View } from "./App";
import SiteForm from "./SiteForm";

interface Props {
  site: string;
  navigate: (v: View) => void;
}

type InlineLog = { text: string; kind: "info" | "ok" | "error" | "url" };

export default function SiteDetail({ site: siteName, navigate }: Props) {
  const [site, setSite] = useState<any>(null);
  const [urls, setUrls] = useState<any[]>([]);
  const [urlFilter, setUrlFilter] = useState<"all" | "pending" | "indexed">("all");
  const [urlSearch, setUrlSearch] = useState("");
  const [urlPage, setUrlPage] = useState(1);
  const [urlTotal, setUrlTotal] = useState(0);
  const PAGE_SIZE = 100;
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [urlAction, setUrlAction] = useState(false);
  const [showEdit, setShowEdit] = useState(false);

  const [panel, setPanel] = useState<{
    visible: boolean;
    running: boolean;
    title: string;
    log: InlineLog[];
    progress: { done: number; total: number } | null;
  }>({ visible: false, running: false, title: "", log: [], progress: null });

  const logRef = useRef<HTMLDivElement>(null);
  const esRef = useRef<EventSource | null>(null);

  function addLog(text: string, kind: InlineLog["kind"] = "info") {
    setPanel((p) => ({ ...p, log: [...p.log, { text, kind }] }));
  }

  function loadSite() {
    api.getSiteStats(siteName).then(setSite);
  }

  function loadUrls(filter = urlFilter, page = urlPage, search = urlSearch) {
    api.getUrls(siteName, filter, page, PAGE_SIZE, search).then((r) => {
      setUrls(r.data);
      setUrlTotal(r.total);
    });
  }

  useEffect(() => {
    loadSite();
    loadUrls();
    return () => esRef.current?.close();
  }, [siteName]);

  useEffect(() => {
    loadUrls(urlFilter, urlPage, urlSearch);
  }, [urlFilter, urlPage, urlSearch]);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [panel.log]);

  // --- Run indexing ---
  function handleRun() {
    if (esRef.current) esRef.current.close();
    setPanel({ visible: true, running: true, title: "Run Indexing", log: [], progress: null });

    const es = new EventSource(api.runStreamUrl(siteName));
    esRef.current = es;

    es.onmessage = (e) => {
      const ev = JSON.parse(e.data);
      if (ev.type === "connected") addLog("Connected…");
      if (ev.type === "status") addLog(ev.message);
      if (ev.type === "urls_found") addLog(`${ev.count} URLs found in sitemap`);
      if (ev.type === "plan") addLog(`${ev.pending} pending · ${ev.capacity} capacity`);
      if (ev.type === "quota_exhausted") addLog(`⚠ ${ev.message}`, "error");
      if (ev.type === "indexed") {
        setPanel((p) => ({
          ...p,
          log: [...p.log, { text: ev.url, kind: "url" }],
          progress: { done: ev.done, total: ev.total },
        }));
        setUrls((prev) =>
          prev.map((u) =>
            u.url === ev.url ? { ...u, indexed: true, indexed_at: new Date().toISOString() } : u
          )
        );
      }
      if (ev.type === "done") {
        addLog(`✓ ${ev.indexed} indexed · ${ev.pending} pending`, "ok");
        setPanel((p) => ({ ...p, running: false }));
        es.close();
        esRef.current = null;
        loadSite();
        loadUrls();
      }
      if (ev.type === "error") {
        addLog(`✗ ${ev.message}`, "error");
        setPanel((p) => ({ ...p, running: false }));
        es.close();
        esRef.current = null;
      }
    };
    es.onerror = () => {
      addLog("Connection lost", "error");
      setPanel((p) => ({ ...p, running: false }));
      es.close();
      esRef.current = null;
    };
  }

  function handleStop() {
    esRef.current?.close();
    esRef.current = null;
    addLog("Stopped by user", "error");
    setPanel((p) => ({ ...p, running: false }));
  }

  // --- Sync GSC ---
  function handleSyncGsc() {
    if (esRef.current) esRef.current.close();
    setPanel({ visible: true, running: true, title: "Sync from Google Search Console", log: [], progress: null });

    const es = new EventSource(api.syncGscStreamUrl(siteName));
    esRef.current = es;

    es.onmessage = (e) => {
      const ev = JSON.parse(e.data);
      if (ev.type === "status") addLog(ev.message);
      if (ev.type === "done") {
        addLog(`✓ ${ev.synced} new URLs marked · ${ev.total} total in GSC`, "ok");
        setPanel((p) => ({ ...p, running: false }));
        es.close();
        esRef.current = null;
        loadSite();
        loadUrls();
      }
      if (ev.type === "error") {
        addLog(`✗ ${ev.message}`, "error");
        setPanel((p) => ({ ...p, running: false }));
        es.close();
        esRef.current = null;
      }
    };
    es.onerror = () => {
      addLog("Connection lost", "error");
      setPanel((p) => ({ ...p, running: false }));
      es.close();
      esRef.current = null;
    };
  }

  // --- Fetch URLs ---
  async function handleFetchUrls() {
    setUrlAction(true);
    try {
      const r = await api.fetchUrls(siteName);
      const parts = [`${r.found} found`, `${r.added} added`, `${r.removed} removed`];
      if (r.reset > 0) parts.push(`${r.reset} reset`);
      addLog(parts.join(" · "), "ok");
      setPanel((p) => ({ ...p, visible: true }));
      loadSite();
      loadUrls();
    } catch (e: any) {
      addLog(`✗ ${e.message}`, "error");
      setPanel((p) => ({ ...p, visible: true }));
    } finally {
      setUrlAction(false);
    }
  }

  // --- URL actions ---
  async function handleMarkIndexed() {
    setUrlAction(true);
    try {
      await api.markIndexed(siteName, [...selected]);
      const now = new Date().toISOString();
      setUrls((prev) =>
        prev.map((u) => selected.has(u.url) ? { ...u, indexed: true, indexed_at: now } : u)
      );
      setSelected(new Set());
      loadSite();
    } catch (e: any) { alert(e.message); }
    finally { setUrlAction(false); }
  }

  async function handleResetSelected() {
    setUrlAction(true);
    try {
      await api.resetUrls(siteName, [...selected]);
      setUrls((prev) =>
        prev.map((u) => selected.has(u.url) ? { ...u, indexed: false, indexed_at: null } : u)
      );
      setSelected(new Set());
      loadSite();
    } catch (e: any) { alert(e.message); }
    finally { setUrlAction(false); }
  }

  async function handleResetAll() {
    if (!confirm("Reset all URLs to pending?")) return;
    setUrlAction(true);
    try {
      await api.resetUrls(siteName, []);
      setUrls((prev) => prev.map((u) => ({ ...u, indexed: false, indexed_at: null })));
      setSelected(new Set());
      loadSite();
    } catch (e: any) { alert(e.message); }
    finally { setUrlAction(false); }
  }

  function toggleSelect(url: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(url) ? next.delete(url) : next.add(url);
      return next;
    });
  }

  function toggleSelectAll() {
    if (selected.size === urls.length) setSelected(new Set());
    else setSelected(new Set(urls.map((u) => u.url)));
  }

  if (!site) return (
    <div className="flex items-center justify-center h-full text-sm" style={{ color: "var(--color-muted)" }}>
      Loading…
    </div>
  );

  const pct = panel.progress && panel.progress.total > 0
    ? Math.round((panel.progress.done / panel.progress.total) * 100)
    : 0;

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">

      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <button
            onClick={() => navigate({ name: "sites" })}
            className="text-xs mb-1 block"
            style={{ color: "var(--color-muted)" }}
          >
            ← Sites
          </button>
          <h1 className="text-xl font-semibold">{site.name}</h1>
          <p className="text-xs mt-0.5" style={{ color: "var(--color-muted)" }}>{site.sitemap_url}</p>
        </div>
        <div className="flex items-center gap-2 shrink-0 pt-5">
          <button
            onClick={() => setShowEdit(true)}
            className="px-4 py-2 rounded-lg text-sm border"
            style={{ borderColor: "var(--color-rim)", color: "var(--color-muted)" }}
            onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.color = "#e6edf3")}
            onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.color = "var(--color-muted)")}
          >
            Edit
          </button>
          {panel.running ? (
            <button
              onClick={handleStop}
              className="px-4 py-2 rounded-lg text-sm font-medium"
              style={{ background: "var(--color-danger)", color: "#fff" }}
            >
              Stop
            </button>
          ) : (
            <button
              onClick={handleRun}
              disabled={site.credentials?.length === 0}
              className="px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-40"
              style={{ background: "var(--color-accent)", color: "#fff" }}
              onMouseEnter={(e) => {
                if (site.credentials?.length > 0)
                  (e.currentTarget as HTMLElement).style.background = "var(--color-accent-hover)";
              }}
              onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.background = "var(--color-accent)")}
              title={site.credentials?.length === 0 ? "No credentials configured" : ""}
            >
              ▶ Run Indexing
            </button>
          )}
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: "Total URLs", value: site.urls_total, color: "#e6edf3" },
          { label: "Sent to Google", value: site.urls_indexed, color: "var(--color-accent-hover)" },
          { label: "Indexed in GSC", value: site.urls_gsc_indexed ?? 0, color: "var(--color-success)" },
          { label: "Pending", value: site.urls_pending, color: site.urls_pending > 0 ? "var(--color-warn)" : "var(--color-muted)" },
        ].map((s) => (
          <div
            key={s.label}
            className="rounded-xl border p-4 text-center"
            style={{ background: "var(--color-navy-card)", borderColor: "var(--color-rim)" }}
          >
            <p className="text-3xl font-bold font-mono" style={{ color: s.color }}>{s.value ?? "—"}</p>
            <p className="text-xs mt-1" style={{ color: "var(--color-muted)" }}>{s.label}</p>
          </div>
        ))}
      </div>

      {/* Quota bars */}
      {site.quota?.length > 0 && (
        <div
          className="rounded-xl border p-4 space-y-3"
          style={{ background: "var(--color-navy-card)", borderColor: "var(--color-rim)" }}
        >
          <p className="text-sm font-medium">Quota today</p>
          {site.quota.map((q: any) => (
            <div key={q.credentials_file}>
              <div className="flex justify-between text-xs mb-1.5" style={{ color: "var(--color-muted)" }}>
                <span className="font-mono">{q.credentials_name}</span>
                <span style={{
                  color: q.remaining === 0 ? "var(--color-danger)" :
                    q.remaining < 50 ? "var(--color-warn)" : "var(--color-success)"
                }}>
                  {q.used} / {q.limit} used · {q.remaining} remaining
                </span>
              </div>
              <div className="rounded-full h-1.5" style={{ background: "var(--color-rim)" }}>
                <div
                  className="h-1.5 rounded-full transition-all"
                  style={{
                    width: `${Math.min(100, (q.used / q.limit) * 100)}%`,
                    background: q.remaining === 0 ? "var(--color-danger)" :
                      q.remaining < 50 ? "var(--color-warn)" : "var(--color-accent)",
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Actions bar */}
      <div
        className="flex flex-wrap gap-2 rounded-xl border p-3"
        style={{ background: "var(--color-navy-card)", borderColor: "var(--color-rim)" }}
      >
        <Btn onClick={handleFetchUrls} disabled={urlAction || panel.running} variant="dark">
          Fetch URLs
        </Btn>
        <Btn onClick={handleSyncGsc} disabled={urlAction || panel.running} variant="purple">
          Sync from GSC
        </Btn>
        <div className="w-px mx-1" style={{ background: "var(--color-rim)" }} />
        <Btn onClick={handleResetAll} disabled={urlAction || panel.running} variant="ghost">
          Reset all
        </Btn>
        {selected.size > 0 && (
          <>
            <div className="w-px mx-1" style={{ background: "var(--color-rim)" }} />
            <span className="self-center text-sm" style={{ color: "var(--color-muted)" }}>
              {selected.size} selected
            </span>
            <Btn onClick={handleMarkIndexed} disabled={urlAction} variant="green">
              Mark sent
            </Btn>
            <Btn onClick={handleResetSelected} disabled={urlAction} variant="warn">
              Reset selected
            </Btn>
          </>
        )}
      </div>

      {/* Progress panel */}
      {panel.visible && (
        <div
          className="rounded-xl border overflow-hidden"
          style={{ background: "var(--color-navy-card)", borderColor: "var(--color-rim)" }}
        >
          <div
            className="flex items-center justify-between px-4 py-2.5 border-b"
            style={{ background: "rgba(0,0,0,0.2)", borderColor: "var(--color-rim)" }}
          >
            <span className="text-xs font-medium" style={{ color: "var(--color-muted)" }}>{panel.title}</span>
            {!panel.running && (
              <button
                onClick={() => setPanel((p) => ({ ...p, visible: false }))}
                className="text-xs"
                style={{ color: "var(--color-muted)" }}
              >
                close
              </button>
            )}
          </div>
          {panel.progress && (
            <div className="px-4 pt-3 pb-1">
              <div className="flex justify-between text-xs mb-1.5" style={{ color: "var(--color-muted)" }}>
                <span>{panel.progress.done} / {panel.progress.total} URLs</span>
                <span>{pct}%</span>
              </div>
              <div className="rounded-full h-1.5" style={{ background: "var(--color-rim)" }}>
                <div
                  className="h-1.5 rounded-full transition-all duration-300"
                  style={{ width: `${pct}%`, background: "var(--color-accent)" }}
                />
              </div>
            </div>
          )}
          <div ref={logRef} className="px-4 py-3 max-h-44 overflow-y-auto space-y-0.5 font-mono text-xs">
            {panel.log.map((entry, i) => (
              <p
                key={i}
                style={{
                  color:
                    entry.kind === "error" ? "var(--color-danger)" :
                    entry.kind === "ok" ? "var(--color-success)" :
                    entry.kind === "url" ? "var(--color-muted)" :
                    "#e6edf3",
                }}
              >
                {entry.kind === "url" ? `✓ ${entry.text}` : entry.text}
              </p>
            ))}
            {panel.running && <p className="animate-pulse" style={{ color: "var(--color-rim)" }}>…</p>}
          </div>
        </div>
      )}

      {/* URL table */}
      <div>
        {/* Search + Filter tabs */}
        <div className="flex items-center gap-3 mb-3">
          <input
            type="text"
            value={urlSearch}
            onChange={(e) => { setUrlSearch(e.target.value); setUrlPage(1); setSelected(new Set()); }}
            placeholder="Search URLs…"
            className="flex-1 px-3 py-1.5 rounded-lg text-sm border outline-none"
            style={{ background: "var(--color-navy-card)", borderColor: "var(--color-rim)", color: "#e6edf3" }}
          />
          <div className="flex gap-1 shrink-0">
          {(["all", "pending", "indexed"] as const).map((f) => (
            <button
              key={f}
              onClick={() => { setUrlFilter(f); setUrlPage(1); setSelected(new Set()); }}
              className="text-sm px-3 py-1.5 rounded-full capitalize transition-colors"
              style={{
                background: urlFilter === f ? "var(--color-accent)" : "rgba(255,255,255,0.05)",
                color: urlFilter === f ? "#fff" : "var(--color-muted)",
              }}
            >
              {f}
            </button>
          ))}
          </div>
        </div>

        <div className="rounded-xl border overflow-hidden" style={{ borderColor: "var(--color-rim)" }}>
          <table className="w-full text-sm">
            <thead>
              <tr style={{ background: "var(--color-navy-card)", borderBottom: `1px solid var(--color-rim)` }}>
                <th className="px-4 py-2.5 w-8">
                  <input
                    type="checkbox"
                    checked={urls.length > 0 && selected.size === urls.length}
                    onChange={toggleSelectAll}
                  />
                </th>
                <th className="text-left px-4 py-2.5 font-medium" style={{ color: "var(--color-muted)" }}>URL</th>
                <th className="text-left px-4 py-2.5 font-medium w-24" style={{ color: "var(--color-muted)" }}>Status</th>
                <th className="text-left px-4 py-2.5 font-medium w-28" style={{ color: "var(--color-muted)" }}>Sent at</th>
                <th className="text-left px-4 py-2.5 font-medium w-24" style={{ color: "var(--color-muted)" }}>Lastmod</th>
                <th className="text-left px-4 py-2.5 font-medium w-28" style={{ color: "var(--color-muted)" }}>GSC</th>
              </tr>
            </thead>
            <tbody>
              {urls.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-10 text-center text-sm" style={{ color: "var(--color-muted)" }}>
                    No URLs
                  </td>
                </tr>
              ) : urls.map((u, i) => (
                <tr
                  key={u.url}
                  style={{
                    background: selected.has(u.url)
                      ? "var(--color-accent-dim)"
                      : i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.015)",
                    borderTop: "1px solid var(--color-rim)",
                  }}
                >
                  <td className="px-4 py-2">
                    <input type="checkbox" checked={selected.has(u.url)} onChange={() => toggleSelect(u.url)} />
                  </td>
                  <td className="px-4 py-2 font-mono text-xs truncate max-w-xs">
                    <a href={u.url} target="_blank" rel="noopener noreferrer" style={{ color: "var(--color-accent-hover)" }}>
                      {u.url}
                    </a>
                  </td>
                  <td className="px-4 py-2">
                    <span
                      className="px-2 py-0.5 rounded-full text-xs font-medium"
                      style={{
                        background: u.indexed ? "rgba(31,111,235,0.15)" : "rgba(210,153,34,0.15)",
                        color: u.indexed ? "var(--color-accent-hover)" : "var(--color-warn)",
                      }}
                    >
                      {u.indexed ? "sent" : "pending"}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-xs" style={{ color: "var(--color-muted)" }}>
                    {u.indexed_at ? new Date(u.indexed_at).toLocaleDateString() : "—"}
                  </td>
                  <td className="px-4 py-2 text-xs" style={{ color: "var(--color-muted)" }}>
                    {u.lastmod ?? "—"}
                  </td>
                  <td className="px-4 py-2">
                    {u.sc_synced_at
                      ? <span className="px-2 py-0.5 rounded-full text-xs font-medium" style={{ background: "rgba(63,185,80,0.15)", color: "var(--color-success)" }}>indexed</span>
                      : <span className="text-xs" style={{ color: "var(--color-rim)" }}>—</span>
                    }
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {urlTotal > PAGE_SIZE && (
          <div className="flex items-center justify-between px-1 py-3 mt-1">
            <span className="text-xs" style={{ color: "var(--color-muted)" }}>
              {(urlPage - 1) * PAGE_SIZE + 1}–{Math.min(urlPage * PAGE_SIZE, urlTotal)} of {urlTotal} URLs
            </span>
            <div className="flex gap-1">
              <button
                onClick={() => setUrlPage((p) => Math.max(1, p - 1))}
                disabled={urlPage === 1}
                className="px-3 py-1 text-sm rounded-lg border disabled:opacity-40"
                style={{ borderColor: "var(--color-rim)", color: "var(--color-muted)" }}
              >
                ← Prev
              </button>
              <button
                onClick={() => setUrlPage((p) => p + 1)}
                disabled={urlPage * PAGE_SIZE >= urlTotal}
                className="px-3 py-1 text-sm rounded-lg border disabled:opacity-40"
                style={{ borderColor: "var(--color-rim)", color: "var(--color-muted)" }}
              >
                Next →
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Edit modal */}
      {showEdit && (
        <SiteForm
          site={site}
          onClose={() => setShowEdit(false)}
          onSaved={() => { setShowEdit(false); loadSite(); }}
        />
      )}
    </div>
  );
}

// --- Small button helper ---
function Btn({
  children,
  onClick,
  disabled,
  variant,
}: {
  children: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
  variant: "dark" | "purple" | "ghost" | "green" | "warn";
}) {
  const styles: Record<string, React.CSSProperties> = {
    dark: { background: "#21262d", color: "#e6edf3", border: "1px solid var(--color-rim)" },
    purple: { background: "#6e40c9", color: "#fff", border: "none" },
    ghost: { background: "transparent", color: "var(--color-muted)", border: "1px solid var(--color-rim)" },
    green: { background: "rgba(63,185,80,0.1)", color: "var(--color-success)", border: "1px solid rgba(63,185,80,0.3)" },
    warn: { background: "rgba(210,153,34,0.1)", color: "var(--color-warn)", border: "1px solid rgba(210,153,34,0.3)" },
  };

  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-40 transition-opacity"
      style={styles[variant]}
    >
      {children}
    </button>
  );
}
