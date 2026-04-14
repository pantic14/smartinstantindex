import { useState, useEffect, useRef } from "react";
import { api } from "../lib/api";
import type { View } from "./App";

interface Props {
  site: string;
  navigate: (v: View) => void;
}

interface UrlRow {
  url: string;
  indexed: boolean;
  indexed_at: string | null;
  lastmod: string | null;
  sc_synced_at: string | null;
}

interface PageData {
  data: UrlRow[];
  total: number;
  page: number;
  page_size: number;
}

interface LogLine {
  type: string;
  message?: string;
  url?: string;
  done?: number;
  total?: number;
  count?: number;
  synced?: number;
  found?: number;
  added?: number;
  removed?: number;
  reset?: number;
}

export default function UrlsTable({ site, navigate }: Props) {
  const [filter, setFilter] = useState<"all" | "pending" | "indexed" | "gsc_indexed">("all");
  const [page, setPage] = useState(1);
  const pageSize = 100;
  const [data, setData] = useState<PageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  // SSE state
  const [syncLog, setSyncLog] = useState<LogLine[]>([]);
  const [syncing, setSyncing] = useState(false);
  const [fetchStatus, setFetchStatus] = useState("");
  const [fetching, setFetching] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  // Run selected state
  const [runLog, setRunLog] = useState<LogLine[]>([]);
  const [running, setRunning] = useState(false);
  const [runProgress, setRunProgress] = useState<{ done: number; total: number } | null>(null);

  async function load() {
    setLoading(true);
    try {
      const result = await api.getUrls(site, filter, page, pageSize);
      setData(result);
      setSelected(new Set());
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    return () => esRef.current?.close();
  }, [site, filter, page]);

  // Fetch URLs from sitemap
  async function handleFetch() {
    setFetching(true);
    setFetchStatus("Fetching sitemap…");
    try {
      const r = await api.fetchUrls(site);
      setFetchStatus(
        `Done — ${r.found} found, ${r.added} added, ${r.removed} removed, ${r.reset} reset`
      );
      load();
    } catch (e: any) {
      setFetchStatus(`Error: ${e.message}`);
    } finally {
      setFetching(false);
    }
  }

  // Sync with GSC via SSE
  function handleSyncGsc() {
    if (esRef.current) {
      esRef.current.close();
    }
    setSyncing(true);
    setSyncLog([]);
    const es = new EventSource(api.syncGscStreamUrl(site));
    esRef.current = es;
    es.onmessage = (e) => {
      const event: LogLine = JSON.parse(e.data);
      setSyncLog((l) => [...l, event]);
      if (event.type === "done" || event.type === "error") {
        es.close();
        setSyncing(false);
        load();
      }
    };
    es.onerror = () => {
      es.close();
      setSyncing(false);
      setSyncLog((l) => [...l, { type: "error", message: "Connection lost" }]);
    };
  }

  // Mark selected as indexed
  async function handleMarkIndexed() {
    if (selected.size === 0) return;
    await api.markIndexed(site, Array.from(selected));
    load();
  }

  // Reset selected (or all)
  async function handleReset(all = false) {
    const urls = all ? [] : Array.from(selected);
    if (!all && urls.length === 0) return;
    const label = all ? "all URLs" : `${urls.length} selected URL(s)`;
    if (!confirm(`Reset ${label} to pending?`)) return;
    await api.resetUrls(site, urls);
    load();
  }

  // Send selected URLs to the Google Indexing API
  async function handleRunSelected() {
    const urlsList = Array.from(selected);
    setSelected(new Set());
    setRunLog([]);
    setRunProgress(null);
    setRunning(true);

    try {
      const response = await api.runSelectedStream(site, urlsList);
      if (!response.ok) {
        setRunLog([{ type: "error", message: "Failed to start indexing" }]);
        setRunning(false);
        return;
      }

      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split("\n\n");
        buffer = chunks.pop() ?? "";

        for (const chunk of chunks) {
          const dataLine = chunk.split("\n").find((l) => l.startsWith("data: "));
          if (!dataLine) continue;
          const ev: LogLine = JSON.parse(dataLine.slice(6));

          if (ev.type === "indexed") {
            setRunLog((l) => [...l, ev]);
            setRunProgress({ done: ev.done!, total: ev.total! });
            setData((prev) => prev
              ? { ...prev, data: prev.data.map((r) => r.url === ev.url ? { ...r, indexed: true, indexed_at: String(new Date().toISOString().slice(0, 10)) } : r) }
              : prev
            );
          } else {
            setRunLog((l) => [...l, ev]);
          }

          if (ev.type === "done" || ev.type === "error") {
            setRunning(false);
            load();
          }
        }
      }
    } catch (e: any) {
      setRunLog([{ type: "error", message: e.message }]);
      setRunning(false);
    }
  }

  function toggleSelect(url: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(url)) next.delete(url);
      else next.add(url);
      return next;
    });
  }

  function toggleAll() {
    if (!data) return;
    if (selected.size === data.data.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(data.data.map((r) => r.url)));
    }
  }

  const totalPages = data ? Math.ceil(data.total / pageSize) : 1;

  return (
    <div className="p-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3 mb-5">
        <button
          onClick={() => navigate({ name: "dashboard" })}
          className="text-sm"
          style={{ color: "var(--color-muted)" }}
        >
          ← Dashboard
        </button>
        <h1 className="text-xl font-semibold">{site}</h1>
      </div>

      {/* Actions bar */}
      <div className="flex flex-wrap items-center gap-2 mb-4">
        {/* Filter */}
        <div className="flex rounded-md overflow-hidden border" style={{ borderColor: "var(--color-rim)" }}>
          {([
            { value: "all", label: "All" },
            { value: "pending", label: "Pending" },
            { value: "indexed", label: "Submitted" },
            { value: "gsc_indexed", label: "Indexed" },
          ] as const).map((f) => (
            <button
              key={f.value}
              onClick={() => { setFilter(f.value); setPage(1); }}
              className="px-3 py-1.5 text-sm"
              style={{
                background: filter === f.value ? "var(--color-accent)" : "var(--color-navy-mid)",
                color: filter === f.value ? "#fff" : "var(--color-muted)",
              }}
            >
              {f.label}
            </button>
          ))}
        </div>

        <div className="flex-1" />

        <button
          onClick={handleFetch}
          disabled={fetching}
          className="px-3 py-1.5 rounded-md text-sm border disabled:opacity-50"
          style={{ borderColor: "var(--color-rim)", color: "var(--color-muted)" }}
        >
          {fetching ? "Fetching…" : "Fetch URLs"}
        </button>

        <button
          onClick={handleSyncGsc}
          disabled={syncing}
          className="px-3 py-1.5 rounded-md text-sm border disabled:opacity-50"
          style={{ borderColor: "var(--color-rim)", color: "var(--color-muted)" }}
        >
          {syncing ? "Syncing…" : "Sync GSC"}
        </button>

        {selected.size > 0 && (
          <>
            <button
              onClick={handleRunSelected}
              disabled={running}
              className="px-3 py-1.5 rounded-md text-sm disabled:opacity-50"
              style={{ background: "var(--color-accent)", color: "#fff" }}
            >
              {running ? "Indexing…" : `Send to index (${selected.size})`}
            </button>
            <button
              onClick={handleMarkIndexed}
              disabled={running}
              className="px-3 py-1.5 rounded-md text-sm disabled:opacity-50"
              style={{ background: "var(--color-success)", color: "#fff" }}
            >
              Mark indexed ({selected.size})
            </button>
            <button
              onClick={() => handleReset(false)}
              disabled={running}
              className="px-3 py-1.5 rounded-md text-sm border disabled:opacity-50"
              style={{ borderColor: "var(--color-warn)", color: "var(--color-warn)" }}
            >
              Reset ({selected.size})
            </button>
          </>
        )}

        <button
          onClick={() => handleReset(true)}
          className="px-3 py-1.5 rounded-md text-sm border"
          style={{ borderColor: "var(--color-danger)", color: "var(--color-danger)" }}
        >
          Reset all
        </button>
      </div>

      {/* Status lines */}
      {fetchStatus && (
        <p className="text-xs mb-3" style={{ color: "var(--color-muted)" }}>
          {fetchStatus}
        </p>
      )}
      {syncLog.length > 0 && (
        <div
          className="mb-3 p-2 rounded-md text-xs font-mono space-y-0.5 max-h-24 overflow-y-auto"
          style={{ background: "rgba(0,0,0,0.25)", border: "1px solid var(--color-rim)" }}
        >
          {syncLog.map((l, i) => (
            <div
              key={i}
              style={{
                color:
                  l.type === "error"
                    ? "var(--color-danger)"
                    : l.type === "done"
                    ? "var(--color-success)"
                    : "var(--color-muted)",
              }}
            >
              {l.type === "done"
                ? `✓ Synced ${l.synced} new URLs (${l.total} total in GSC)`
                : l.message || l.type}
            </div>
          ))}
        </div>
      )}

      {runLog.length > 0 && (
        <div
          className="mb-3 p-2 rounded-md text-xs font-mono space-y-0.5 max-h-32 overflow-y-auto"
          style={{ background: "rgba(0,0,0,0.25)", border: "1px solid var(--color-rim)" }}
        >
          {runProgress && (
            <div className="mb-1.5" style={{ color: "var(--color-muted)" }}>
              {runProgress.done} / {runProgress.total} URLs
            </div>
          )}
          {runLog.map((l, i) => (
            <div
              key={i}
              style={{
                color:
                  l.type === "error"
                    ? "var(--color-danger)"
                    : l.type === "done"
                    ? "var(--color-success)"
                    : l.type === "indexed"
                    ? "var(--color-muted)"
                    : "var(--color-muted)",
              }}
            >
              {l.type === "indexed"
                ? `✓ ${l.url}`
                : l.type === "done"
                ? `Done — ${l.done ?? 0} sent`
                : l.message || l.type}
            </div>
          ))}
          {running && <div style={{ color: "var(--color-muted)", opacity: 0.5 }}>…</div>}
        </div>
      )}

      {/* Table */}
      <div
        className="rounded-xl border overflow-hidden"
        style={{ borderColor: "var(--color-rim)" }}
      >
        <table className="w-full text-sm">
          <thead>
            <tr style={{ background: "var(--color-navy-card)", borderBottom: "1px solid var(--color-rim)" }}>
              <th className="w-10 px-4 py-3 text-left">
                <input
                  type="checkbox"
                  checked={!!data && selected.size === data.data.length && data.data.length > 0}
                  onChange={toggleAll}
                />
              </th>
              <th className="px-4 py-3 text-left font-medium" style={{ color: "var(--color-muted)" }}>
                URL
              </th>
              <th className="w-24 px-4 py-3 text-left font-medium" style={{ color: "var(--color-muted)" }}>
                Status
              </th>
              <th className="w-32 px-4 py-3 text-left font-medium" style={{ color: "var(--color-muted)" }}>
                Indexed at
              </th>
              <th className="w-32 px-4 py-3 text-left font-medium" style={{ color: "var(--color-muted)" }}>
                Lastmod
              </th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center" style={{ color: "var(--color-muted)" }}>
                  Loading…
                </td>
              </tr>
            ) : data?.data.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center" style={{ color: "var(--color-muted)" }}>
                  No URLs
                </td>
              </tr>
            ) : (
              data?.data.map((row, i) => (
                <tr
                  key={row.url}
                  style={{
                    background: i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.015)",
                    borderTop: "1px solid var(--color-rim)",
                  }}
                >
                  <td className="px-4 py-2">
                    <input
                      type="checkbox"
                      checked={selected.has(row.url)}
                      onChange={() => toggleSelect(row.url)}
                    />
                  </td>
                  <td className="px-4 py-2 font-mono text-xs truncate max-w-xs" title={row.url}>
                    <a
                      href={row.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ color: "var(--color-accent-hover)" }}
                    >
                      {row.url}
                    </a>
                  </td>
                  <td className="px-4 py-2">
                    <span
                      className="px-2 py-0.5 rounded-full text-xs"
                      style={{
                        background: row.indexed ? "rgba(63,185,80,0.15)" : "rgba(210,153,34,0.15)",
                        color: row.indexed ? "var(--color-success)" : "var(--color-warn)",
                      }}
                    >
                      {row.indexed ? "indexed" : "pending"}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-xs" style={{ color: "var(--color-muted)" }}>
                    {row.indexed_at || "—"}
                  </td>
                  <td className="px-4 py-2 text-xs" style={{ color: "var(--color-muted)" }}>
                    {row.lastmod || "—"}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {data && totalPages > 1 && (
        <div className="flex items-center justify-between mt-4 text-sm">
          <span style={{ color: "var(--color-muted)" }}>
            {data.total} URLs · page {page} of {totalPages}
          </span>
          <div className="flex gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="px-3 py-1 rounded border disabled:opacity-40"
              style={{ borderColor: "var(--color-rim)", color: "var(--color-muted)" }}
            >
              ← Prev
            </button>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="px-3 py-1 rounded border disabled:opacity-40"
              style={{ borderColor: "var(--color-rim)", color: "var(--color-muted)" }}
            >
              Next →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
