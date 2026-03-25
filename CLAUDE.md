# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

SmartInstantIndex is a Python tool that submits website URLs to Google Search via the Google Indexing API. It reads URLs from XML sitemaps, tracks indexing state in a JSON file, and respects the 200 URLs/day quota per GCP project.

## Running the tool

```bash
pip install -r requirements.txt
python index.py
```

There are no tests, no linter config, and no build system beyond `requirements.txt`.

## Architecture

**Entry point:** `index.py` — orchestrates the full pipeline per-site:
1. Load and normalize `config.json` → site list
2. Fetch URLs from sitemap via `smartinstantindex/sitemaps.py`
3. Filter URLs (extensions, patterns) via `smartinstantindex/utils.py`
4. Diff against stored state (`urls_{name}.json`), apply lastmod resets
5. Submit up to 200 pending URLs via `smartinstantindex/indexing.py`
6. Update quota counter in `quota.json`

**`smartinstantindex/sitemaps.py`** — recursively parses sitemap XML (handles sitemap indexes). Returns `dict[url, lastmod|None]`.

**`smartinstantindex/indexing.py`** — authenticates with a Google service account (`credentials.json`) and POSTs each URL to the Indexing API v3.

**`smartinstantindex/utils.py`** — JSON I/O, logger setup, and helpers: `normalize_config`, `migrate_urls`, `filter_urls`, `update_quota`, `update_quota_batch`.

## Data files

| File | Purpose |
|------|---------|
| `config.json` | Site configuration (sitemap URL, credentials path, filter rules) |
| `urls_{name}.json` | Per-site indexing state: `{url: {"indexed": bool, "lastmod": str\|null}}` |
| `quota.json` | Daily quota tracking per credentials file: `{creds_file: {"date": "...", "used": N}}` |
| `credentials.json` | Google service account key (not committed) |

**Legacy format support:** `config.json` with a bare `sitemap_url` key (v1) and `urls.json` with `{url: bool}` values are auto-migrated on first run.

## GUI

`app.py` — desktop GUI built with CustomTkinter. Screens: Dashboard, URLs, Sites, Settings.
`build.py` — packages the GUI as a standalone executable via PyInstaller: `pyinstaller --onefile --windowed --name SmartInstantIndex app.py`

## Google API quota note

The 200 URLs/day limit is **per GCP project**, not per service account. Two service accounts under the same project share the same quota.
