import { useState, useEffect } from "react";
import { api } from "../lib/api";

interface Site {
  name: string;
  sitemap_url: string;
  site_url: string;
  track_lastmod: boolean;
  credentials: string[];
  skip_extensions: string[];
  exclude_patterns: string[];
  include_patterns: string[];
}

interface Props {
  site: Site | null;
  onClose: () => void;
  onSaved: () => void;
}

const DEFAULT_SKIP = [".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".zip", ".mp4", ".mp3"];

export default function SiteForm({ site, onClose, onSaved }: Props) {
  const [name, setName] = useState(site?.name ?? "");
  const [sitemapUrl, setSitemapUrl] = useState(site?.sitemap_url ?? "");
  const [siteUrl, setSiteUrl] = useState(site?.site_url ?? "");
  const [trackLastmod, setTrackLastmod] = useState(site?.track_lastmod ?? false);
  const [credentials, setCredentials] = useState<string[]>(site?.credentials ?? []);
  const [skipExtensions, setSkipExtensions] = useState(
    (site?.skip_extensions ?? DEFAULT_SKIP).join(", ")
  );
  const [excludePatterns, setExcludePatterns] = useState(
    (site?.exclude_patterns ?? []).join("\n")
  );
  const [includePatterns, setIncludePatterns] = useState(
    (site?.include_patterns ?? []).join("\n")
  );
  const [availableCreds, setAvailableCreds] = useState<{ filename: string; client_email: string }[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.getCredentials().then(setAvailableCreds).catch(() => {});
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      const payload = {
        name,
        sitemap_url: sitemapUrl,
        site_url: siteUrl,
        track_lastmod: trackLastmod,
        credentials,
        skip_extensions: skipExtensions
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        exclude_patterns: excludePatterns.split("\n").map((s) => s.trim()).filter(Boolean),
        include_patterns: includePatterns.split("\n").map((s) => s.trim()).filter(Boolean),
      };
      if (site) {
        await api.updateSite(site.name, payload);
      } else {
        await api.createSite(payload);
      }
      onSaved();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  function toggleCred(filename: string) {
    setCredentials((prev) =>
      prev.includes(filename)
        ? prev.filter((c) => c !== filename)
        : [...prev, filename]
    );
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,0.6)" }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        className="w-full max-w-lg rounded-xl border overflow-hidden"
        style={{ background: "var(--color-navy-mid)", borderColor: "var(--color-rim)" }}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between px-5 py-4 border-b"
          style={{ borderColor: "var(--color-rim)" }}
        >
          <h2 className="font-semibold">{site ? "Edit site" : "New site"}</h2>
          <button
            onClick={onClose}
            className="text-xl leading-none"
            style={{ color: "var(--color-muted)" }}
          >
            ×
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-5 space-y-4 overflow-y-auto max-h-[70vh]">
          {error && (
            <p className="text-sm p-3 rounded-md" style={{ background: "rgba(248,81,73,0.1)", color: "var(--color-danger)" }}>
              {error}
            </p>
          )}

          <Field label="Site name" required>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={!!site}
              required
              placeholder="my-site"
              className="input"
            />
          </Field>

          <Field label="Sitemap URL" required>
            <input
              value={sitemapUrl}
              onChange={(e) => setSitemapUrl(e.target.value)}
              required
              placeholder="https://example.com/sitemap.xml"
              className="input"
            />
          </Field>

          <Field label="Search Console property (optional)">
            <input
              value={siteUrl}
              onChange={(e) => setSiteUrl(e.target.value)}
              placeholder="https://example.com/"
              className="input"
            />
          </Field>

          <Field label="Credentials">
            {availableCreds.length === 0 ? (
              <p className="text-sm" style={{ color: "var(--color-muted)" }}>
                No credentials available. Upload a service account JSON in Settings.
              </p>
            ) : (
              <div className="space-y-1.5">
                {availableCreds.map((c) => (
                  <label key={c.filename} className="flex items-center gap-2 cursor-pointer text-sm">
                    <input
                      type="checkbox"
                      checked={credentials.includes(c.filename)}
                      onChange={() => toggleCred(c.filename)}
                      className="rounded"
                    />
                    <span className="font-mono text-xs truncate">{c.client_email}</span>
                  </label>
                ))}
              </div>
            )}
          </Field>

          <label className="flex items-center gap-2 cursor-pointer text-sm">
            <input
              type="checkbox"
              checked={trackLastmod}
              onChange={(e) => setTrackLastmod(e.target.checked)}
              className="rounded"
            />
            <span>Track lastmod (re-index when sitemap lastmod changes)</span>
          </label>

          <Field label="Skip extensions (comma-separated)">
            <input
              value={skipExtensions}
              onChange={(e) => setSkipExtensions(e.target.value)}
              placeholder=".pdf, .jpg, .png"
              className="input"
            />
          </Field>

          <Field label="Exclude patterns (one regex per line)">
            <textarea
              value={excludePatterns}
              onChange={(e) => setExcludePatterns(e.target.value)}
              rows={3}
              placeholder="/admin/.*\n/tag/.*"
              className="input resize-none font-mono text-xs"
            />
          </Field>

          <Field label="Include patterns (one regex per line, empty = all)">
            <textarea
              value={includePatterns}
              onChange={(e) => setIncludePatterns(e.target.value)}
              rows={3}
              placeholder="/blog/.*"
              className="input resize-none font-mono text-xs"
            />
          </Field>

          <div className="flex gap-2 pt-2">
            <button
              type="submit"
              disabled={saving}
              className="flex-1 py-2 rounded-md text-sm font-medium disabled:opacity-50"
              style={{ background: "var(--color-accent)", color: "#fff" }}
            >
              {saving ? "Saving…" : site ? "Save changes" : "Create site"}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="flex-1 py-2 rounded-md text-sm border"
              style={{ borderColor: "var(--color-rim)", color: "var(--color-muted)" }}
            >
              Cancel
            </button>
          </div>
        </form>
      </div>

      <style>{`
        .input {
          width: 100%;
          padding: 0.5rem 0.75rem;
          border-radius: 0.375rem;
          border: 1px solid var(--color-rim);
          background: var(--color-navy-card);
          color: #e6edf3;
          font-size: 0.875rem;
          outline: none;
        }
        .input:focus {
          border-color: var(--color-accent);
        }
        .input:disabled {
          opacity: 0.5;
        }
      `}</style>
    </div>
  );
}

function Field({ label, required, children }: { label: string; required?: boolean; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <label className="text-xs font-medium" style={{ color: "var(--color-muted)" }}>
        {label}
        {required && <span style={{ color: "var(--color-danger)" }}> *</span>}
      </label>
      {children}
    </div>
  );
}
