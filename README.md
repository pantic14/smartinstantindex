# SmartInstantIndex by Pantic14

A tool to automatically submit your website URLs to Google Search via the Google Indexing API. Supports multiple sites, URL filtering, lastmod tracking, and includes a desktop GUI.

## Features

- Indexes up to 200 URLs/day per Google Cloud Project
- Reads URLs from XML sitemaps (including sitemap indexes)
- Tracks indexing state so it never re-submits already indexed URLs
- Filters URLs by extension, exclude patterns, and include patterns (whitelist)
- Resets URLs automatically when `lastmod` changes in the sitemap
- Multi-site support from a single `config.json`
- Desktop GUI (CustomTkinter) with Dashboard, URLs, Sites, and Settings screens

## Setup

### 1. Install dependencies

```shell
pip install -r requirements.txt
```

### 2. Create a Google Cloud Project and enable the Indexing API

Visit [https://console.cloud.google.com/apis/api/indexing.googleapis.com](https://console.cloud.google.com/apis/api/indexing.googleapis.com) and click **ENABLE**.

### 3. Create a Service Account

Follow the guide: [https://developers.google.com/search/apis/indexing-api/v3/prereqs#create-service-account](https://developers.google.com/search/apis/indexing-api/v3/prereqs#create-service-account)

Save the service account key as `credentials.json` in the project folder. This allows indexing **200 pages/day** (Google API limit per GCP project).

### 4. Add the service account to Google Search Console

Guide: [https://developers.google.com/search/apis/indexing-api/v3/prereqs#verify-site](https://developers.google.com/search/apis/indexing-api/v3/prereqs#verify-site)

Give the service account the `Owner` role.

### 5. Configure `config.json`

```json
{
    "sites": [
        {
            "name": "mysite",
            "sitemap_url": "https://example.com/sitemap.xml",
            "credentials": "credentials.json",
            "urls_file": "urls_mysite.json",
            "track_lastmod": false,
            "skip_extensions": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".pdf", ".mp4", ".zip"],
            "exclude_patterns": [],
            "include_patterns": []
        }
    ]
}
```

## Usage

### CLI

```shell
python index.py
```

### Desktop GUI

```shell
python app.py
```

Or download the standalone `.exe` from the Releases page (no Python required).

### Build the executable

```shell
python build.py
```

Output: `dist/SmartInstantIndex.exe` (Windows) / `dist/SmartInstantIndex` (Mac/Linux)

## Quota note

The 200 URLs/day limit is **per GCP project**, not per service account. Two service accounts under the same project share the same quota.

## Questions and Issues

Open a new issue on GitHub.
