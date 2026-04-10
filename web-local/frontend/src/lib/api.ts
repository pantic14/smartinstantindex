const BASE = "http://localhost:7842";

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? res.statusText);
  }
  return res.json();
}

export const api = {
  // Sites
  getSites: () => req<any[]>("GET", "/api/sites"),
  getSiteStats: (name: string) => req<any>("GET", `/api/sites/${name}/stats`),
  createSite: (body: any) => req<any>("POST", "/api/sites", body),
  updateSite: (name: string, body: any) => req<any>("PUT", `/api/sites/${name}`, body),
  deleteSite: (name: string) => req<any>("DELETE", `/api/sites/${name}`),

  // URLs
  getUrls: (name: string, filter = "all", page = 1, pageSize = 100, search = "") =>
    req<any>("GET", `/api/sites/${name}/urls?filter=${filter}&page=${page}&page_size=${pageSize}&search=${encodeURIComponent(search)}`),
  fetchUrls: (name: string) => req<any>("POST", `/api/sites/${name}/fetch-urls`),
  markIndexed: (name: string, urls: string[]) =>
    req<any>("POST", `/api/sites/${name}/mark-indexed`, { urls }),
  resetUrls: (name: string, urls: string[]) =>
    req<any>("POST", `/api/sites/${name}/reset`, { urls }),

  // Credentials
  getCredentials: () => req<any[]>("GET", "/api/credentials"),
  deleteCredential: (filename: string) => req<any>("DELETE", `/api/credentials/${filename}`),

  // SSE URLs (opened by EventSource, not fetch)
  runStreamUrl: (name: string) => `${BASE}/api/sites/${name}/run/stream`,
  syncGscStreamUrl: (name: string) => `${BASE}/api/sites/${name}/sync-gsc/stream`,
};
