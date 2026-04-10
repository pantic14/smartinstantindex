# SmartInstantIndex

Submit your website URLs to Google Search in minutes, not weeks.

SmartInstantIndex uses the Google Indexing API to notify Google of new or updated pages directly, bypassing the normal crawl queue. It reads URLs from your XML sitemap, tracks which ones have been submitted, and respects Google's 200 URLs/day quota per GCP project.

Available as a **local web app** (Windows/Mac/Linux) or as a **CLI tool**.

[Download the latest release](../../releases/latest) · [Report an issue](../../issues)

---

## Features

- Indexes up to 200 URLs/day per Google Cloud Project
- Reads URLs from XML sitemaps (including sitemap indexes)
- Tracks indexing state — never re-submits already indexed URLs
- Filters URLs by extension, exclude patterns, and include patterns (whitelist) with regex support
- Resets URLs automatically when `lastmod` changes in the sitemap
- Multi-site support with multiple credentials per site
- Google Search Console integration — sync which pages are confirmed as indexed
- Multiply daily quota by assigning credentials from different GCP projects
- Search across all URLs instantly
- Runs as a local web app with a system tray icon — no browser extension or cloud account needed

---

## Quick start (no Python required)

1. Download the binary for your OS from the [Releases page](../../releases/latest):
   - `SmartInstantIndex-windows.exe`
   - `SmartInstantIndex-macos`
   - `SmartInstantIndex-linux`

2. Run it. Your browser opens automatically at `http://localhost:7842`.

3. A tray icon appears in your taskbar. Right-click it to reopen the app or quit.

4. Go to **Settings** to upload your Google service account credentials, then **Sites** to add your first site.

> The app stores all data (config, URL state, quota) in the same folder as the executable.

---

## Google credentials — step by step

You need a Google service account to use the Indexing API.

### Step 1 — Create a Google Cloud project

Go to [console.cloud.google.com](https://console.cloud.google.com), click the project selector → **New Project**, give it a name and click **Create**.

### Step 2 — Enable the Web Search Indexing API

In the search bar type `Web Search Indexing API`, make sure your project is selected in the top-left, then click **ENABLE**.

### Step 3 — Create a service account and download its key

Menu → **IAM & Admin** → **Service Accounts** → **+ Create Service Account** → enter any name → **Create and Continue** → **Done**.

Click the account you just created → **Keys** tab → **Add Key** → **Create new key** → JSON → **Create**.

A `.json` file is downloaded — this is your credentials file.

### Step 4 — Add the service account to Google Search Console

Copy the service account email (e.g. `name@project.iam.gserviceaccount.com`).

Go to [search.google.com/search-console](https://search.google.com/search-console), select your property → **Settings** → **Users and permissions** → **Add user** → paste the email → role **Owner** → Add.

### Step 5 — Upload in SmartInstantIndex

Go to **Settings** in the app → upload the JSON file. Then open your site → **Edit** → assign the credentials.

---

## Multiplying the daily quota

Google's 200 URLs/day limit is **per GCP project**, not per service account. By assigning credentials from multiple different GCP projects to the same site, SmartInstantIndex automatically rotates to the next when the current one hits its daily limit.

**Example:** 3 credentials from 3 different projects → 600 URLs/day for the same site.

Repeat the steps above for each additional GCP project, upload each JSON file in Settings, and assign them all to your site.

---

## Sync with Google Search Console

The **Sync from GSC** feature queries Google Search Console for all confirmed-indexed pages and marks matching URLs in the app. To use it:

1. Enable the **Google Search Console API** in your GCP project (same steps as above, search for `Google Search Console API`).
2. In your site settings, set the **Search Console Property URL**:
   - Domain property → `sc-domain:example.com` (verified via DNS)
   - URL-prefix property → `https://example.com/` (verified via HTML file or meta tag)

---

## CLI usage (Python required)

```shell
pip install -r requirements.txt
python index.py
```

Runs one full indexing cycle for all sites in `config.json`. Useful for running SmartInstantIndex from a server or cron job.

### config.json format

```json
{
    "sites": [
        {
            "name": "my-site",
            "sitemap_url": "https://example.com/sitemap.xml",
            "credentials": ["credentials.json"],
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

### Data files

| File | Purpose |
|------|---------|
| `config.json` | Site configuration |
| `credentials.json` | Google Service Account key — never commit this |
| `urls_{name}.json` | Per-site indexing state |
| `quota.json` | Daily quota tracking |

---

## Running from source

```shell
pip install -r requirements.txt

# Local web app
python app_web.py

# CLI only
python index.py

# Build standalone executable
python build.py
```

---

## Questions and issues

Open a new issue on GitHub.

---

Developed by [escala14.com](https://escala14.com) · MIT License
