import { useState, useEffect, useRef } from "react";
import { api } from "../lib/api";

interface Credential {
  filename: string;
  client_email: string;
  project_id: string;
}

export default function Settings() {
  const [creds, setCreds] = useState<Credential[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [uploadSuccess, setUploadSuccess] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  async function load() {
    try {
      const data = await api.getCredentials();
      setCreds(data);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setUploadError("");
    setUploadSuccess("");
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch("http://localhost:7842/api/credentials/upload", {
        method: "POST",
        body: form,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail ?? res.statusText);
      }
      const data = await res.json();
      setUploadSuccess(`Uploaded: ${data.client_email}`);
      load();
    } catch (e: any) {
      setUploadError(e.message);
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  async function handleDelete(filename: string) {
    if (!confirm(`Delete credential "${filename}"?`)) return;
    await api.deleteCredential(filename);
    load();
  }

  return (
    <div className="p-6 max-w-2xl mx-auto">
      <h1 className="text-xl font-semibold mb-6">Settings</h1>

      {/* Upload */}
      <section
        className="rounded-xl border p-5 mb-6"
        style={{ background: "var(--color-navy-card)", borderColor: "var(--color-rim)" }}
      >
        <h2 className="font-semibold mb-1">Google Service Account</h2>
        <p className="text-sm mb-4" style={{ color: "var(--color-muted)" }}>
          Upload your Google service account JSON file to authenticate with the
          Google Indexing API. Each service account allows up to 200 URL
          submissions per day.
        </p>

        <label
          className="flex flex-col items-center justify-center gap-2 border-2 border-dashed rounded-lg p-8 cursor-pointer transition-colors"
          style={{ borderColor: "var(--color-rim)" }}
          onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.borderColor = "var(--color-accent)")}
          onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.borderColor = "var(--color-rim)")}
        >
          <span className="text-2xl">⬆</span>
          <span className="text-sm font-medium">
            {uploading ? "Uploading…" : "Click to upload service account JSON"}
          </span>
          <span className="text-xs" style={{ color: "var(--color-muted)" }}>
            Must be a Google service account key file
          </span>
          <input
            ref={inputRef}
            type="file"
            accept=".json"
            className="hidden"
            onChange={handleUpload}
            disabled={uploading}
          />
        </label>

        {uploadError && (
          <p className="mt-3 text-sm" style={{ color: "var(--color-danger)" }}>
            {uploadError}
          </p>
        )}
        {uploadSuccess && (
          <p className="mt-3 text-sm" style={{ color: "var(--color-success)" }}>
            ✓ {uploadSuccess}
          </p>
        )}
      </section>

      {/* Credentials list */}
      <section>
        <h2 className="font-semibold mb-3">Stored credentials</h2>

        {loading ? (
          <p style={{ color: "var(--color-muted)" }}>Loading…</p>
        ) : creds.length === 0 ? (
          <div
            className="border border-dashed rounded-lg p-8 text-center"
            style={{ borderColor: "var(--color-rim)", color: "var(--color-muted)" }}
          >
            No credentials stored yet.
          </div>
        ) : (
          <div className="space-y-2">
            {creds.map((c) => (
              <div
                key={c.filename}
                className="flex items-center justify-between gap-4 rounded-lg border px-4 py-3"
                style={{
                  background: "var(--color-navy-card)",
                  borderColor: "var(--color-rim)",
                }}
              >
                <div className="min-w-0">
                  <p className="text-sm font-mono truncate">{c.client_email}</p>
                  <p className="text-xs" style={{ color: "var(--color-muted)" }}>
                    {c.project_id} · {c.filename}
                  </p>
                </div>
                <button
                  onClick={() => handleDelete(c.filename)}
                  className="shrink-0 text-xs px-3 py-1.5 rounded border transition-colors"
                  style={{ borderColor: "var(--color-danger)", color: "var(--color-danger)" }}
                >
                  Delete
                </button>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Info */}
      <section
        className="mt-6 rounded-xl border p-5"
        style={{ background: "var(--color-navy-card)", borderColor: "var(--color-rim)" }}
      >
        <h2 className="font-semibold mb-2">About quota</h2>
        <p className="text-sm" style={{ color: "var(--color-muted)" }}>
          The Google Indexing API allows{" "}
          <strong className="text-white">200 URL submissions per day</strong> per GCP project.
          Note that the quota is per project, not per service account — multiple service
          accounts under the same project share the same daily limit.
          Add service accounts from different GCP projects to increase your daily capacity.
        </p>
      </section>
    </div>
  );
}
