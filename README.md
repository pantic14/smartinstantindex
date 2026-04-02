# SmartInstantIndex

Submit your website URLs to Google Search in minutes, not weeks.

SmartInstantIndex uses the Google Indexing API to notify Google of new or updated pages directly, bypassing the normal crawl queue. It reads URLs from your XML sitemap, tracks which ones have been submitted, and respects Google's 200 URLs/day quota per GCP project.

Available as a **desktop GUI** (Windows/Mac/Linux) or as a **CLI tool**.

[Download the latest release](../../releases/latest) · [Report an issue](../../issues)

---

## Features

- Indexes up to 200 URLs/day per Google Cloud Project
- Reads URLs from XML sitemaps (including sitemap indexes)
- Tracks indexing state — never re-submits already indexed URLs
- Filters URLs by extension, exclude patterns, and include patterns (whitelist)
- Resets URLs automatically when `lastmod` changes in the sitemap
- Multi-site support from a single `config.json`
- Google Search Console integration — fetch which pages are actually indexed
- Desktop GUI (CustomTkinter) with Dashboard, URLs, Sites, Settings, and Help screens

## Requirements

- Python 3.9+
- A Google Cloud Project with the Indexing API enabled
- A Google Service Account with Owner access in Google Search Console

## Setup

### 1. Install dependencies

```shell
pip install -r requirements.txt
```

### 2. Create a Google Cloud Project and enable the Indexing API

Visit [console.cloud.google.com/apis/api/indexing.googleapis.com](https://console.cloud.google.com/apis/api/indexing.googleapis.com) and click **ENABLE**.

### 3. Create a Service Account

Follow Google's guide: [prereqs#create-service-account](https://developers.google.com/search/apis/indexing-api/v3/prereqs#create-service-account)

Download the JSON key and save it as `credentials.json` in the project folder.

> **Security warning:** Never commit `credentials.json` to version control. It is already listed in `.gitignore`. See `credentials.example.json` for the expected file structure.

### 4. Add the service account to Google Search Console

Guide: [prereqs#verify-site](https://developers.google.com/search/apis/indexing-api/v3/prereqs#verify-site)

Grant the service account the `Owner` role on your property.

### 5. Configure `config.json`

Copy `config.example.json` to `config.json` and fill in your site details:

```json
{
    "sites": [
        {
            "name": "my-site",
            "sitemap_url": "https://example.com/sitemap.xml",
            "credentials": "credentials.json",
            "urls_file": "urls_my-site.json",
            "site_url": "sc-domain:example.com",
            "track_lastmod": false,
            "skip_extensions": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".pdf", ".mp4", ".zip"],
            "exclude_patterns": [],
            "include_patterns": []
        }
    ]
}
```

`site_url` must match exactly how the property appears in Google Search Console (e.g. `sc-domain:example.com` for domain properties).

## Usage

### Desktop GUI

```shell
python app.py
```

Or download the standalone binary from the [Releases page](../../releases/latest) — no Python required.

### CLI

```shell
python index.py
```

Runs one full indexing cycle for all sites in `config.json`.

### Build the executable

```shell
python build.py
```

Produces `dist/SmartInstantIndex.exe` (Windows) or `dist/SmartInstantIndex` (Mac/Linux).

## Quota note

The 200 URLs/day limit is **per GCP project**, not per service account. Two service accounts under the same project share the same quota.

## Data files

| File | Purpose |
|------|---------|
| `config.json` | Site configuration |
| `credentials.json` | Google Service Account key (never commit this) |
| `urls_{name}.json` | Per-site indexing state |
| `quota.json` | Daily quota tracking |

## Questions and Issues

Open a new issue on GitHub.

---

Developed by [escala14.com](https://escala14.com) · MIT License
