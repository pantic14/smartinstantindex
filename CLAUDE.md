# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

SmartInstantIndex is a Python tool that submits website URLs to Google Search via the Google Indexing API. It reads URLs from XML sitemaps, tracks indexing state in a JSON file, and respects the 200 URLs/day quota per GCP project.

## Running the tool

```bash
pip install -r requirements.txt
python index.py        # CLI: run indexing once
python app.py          # GUI: launch the CustomTkinter desktop app
python app_web.py      # Web UI: start FastAPI on localhost:7842 + system tray icon
python build.py        # package app_web.py as standalone exe via PyInstaller
```

**Web frontend** (required before running `app_web.py` or `build.py`):
```bash
cd web_local/frontend
npm install
npm run build          # outputs to web_local/frontend/dist/
```

There are no tests, no linter config, and no build system beyond `requirements.txt`.

The `smartinstantindex/` package is also installable via `pip install .` (see `pyproject.toml`).

## Architecture

There are two GUI entry points:

**`app.py`** — CustomTkinter desktop GUI (legacy). Screens: Dashboard, URLs, Sites, Settings, Help. Indexing runs in a background thread.

**`app_web.py`** — Web-based app (current). Starts a FastAPI server on `localhost:7842`, opens the browser, and shows a system tray icon (pystray). Serves the compiled Astro frontend as static files. Intended for packaging via PyInstaller.

**`index.py`** — CLI entry point; orchestrates the full pipeline per-site:
1. Load and normalize `config.json` → site list
2. Fetch URLs from sitemap via `smartinstantindex/sitemaps.py`
3. Filter URLs (extensions, patterns) via `smartinstantindex/utils.py`
4. Diff against stored state (`urls_{name}.json`), apply lastmod resets
5. Submit up to 200 pending URLs via `smartinstantindex/indexing.py`
6. Update quota counter in `quota.json`

### Core package (`smartinstantindex/`)

**`sitemaps.py`** — recursively parses sitemap XML (handles sitemap indexes). Returns `dict[url, lastmod|None]`.

**`indexing.py`** — authenticates with a Google service account and POSTs each URL to the Indexing API v3.

**`utils.py`** — JSON I/O, logger setup, and helpers: `normalize_config`, `migrate_urls`, `filter_urls`, `build_indexing_plan`, `update_quota_batch`, `get_quota_remaining`.

**`searchconsole.py`** — queries the Google Search Console API to fetch all indexed pages (pages with impressions in the last N months). Used to sync `gsc_indexed` state. Requires the "Google Search Console API" enabled separately from the Indexing API. Two variants: `fetch_indexed_pages` (file path) and `fetch_indexed_pages_from_dict` (credentials dict, used by cloud).

### Web UI (`web_local/`)

**`web_local/backend/routes.py`** — FastAPI app that serves the Astro static build and exposes the REST + SSE API. Reads `DATA_DIR` and `SMARTINDEX_STATIC_DIR` from environment variables (set by `app_web.py`). Imports from `smartinstantindex.*` directly.

**`web_local/frontend/`** — Astro 6 + React + Tailwind 4 frontend. Build output goes to `web_local/frontend/dist/`, which PyInstaller bundles as `static/`.

## Data files

| File | Purpose |
|------|---------|
| `config.json` | Site configuration (sitemap URL, credentials list, filter rules, GSC site_url) |
| `urls_{name}.json` | Per-site indexing state: `{url: {"indexed": bool, "lastmod": str\|null, "gsc_indexed": bool, "sc_synced_at": str\|null}}` |
| `quota.json` | Daily quota tracking per credentials file: `{creds_file: {"date": "...", "used": N}}` |
| `credentials*.json` | Google service account keys (not committed) |

**`config.json` site fields:** `name`, `sitemap_url`, `credentials` (list of filenames), `site_url` (GSC property URL), `urls_file`, `track_lastmod`, `skip_extensions`, `exclude_patterns`, `include_patterns`, `schedule_enabled`, `schedule_hour`.

**Legacy format support:** `config.json` with a bare `sitemap_url` key (v1) and `urls.json` with `{url: bool}` values are auto-migrated on first run.

## File path resolution

`DATA_DIR` is the exe folder when frozen (PyInstaller), the script folder otherwise. All JSON data files are resolved relative to `DATA_DIR`. The web static files are bundled into `sys._MEIPASS/static` when frozen.

## Known gotcha in sitemaps.py

`fetch_urls_from_sitemap_recursive` uses a mutable default argument (`visited_sitemaps=set()`). This set persists across calls in the same process, so running indexing more than once per process (e.g. via the GUI's "Run Indexing" button) will skip all sitemaps visited in prior runs. The global `ALL_URLS` reset partially mitigates this but the visited set is never cleared.

## Google API quota note

The 200 URLs/day limit is **per GCP project**, not per service account. Two service accounts under the same project share the same quota. A site can have multiple credentials files (rotated round-robin to multiply effective quota).
