import json
import logging
import logging.config
import os
import re
from datetime import date, datetime, timezone


def load_json(file_path):
    try:
        with open(file_path, 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        return {}


def save_urls_to_file(urls, file_path):
    with open(file_path, 'w') as file:
        json.dump(urls, file, indent=4)


def create_logger() -> logging.Logger:
    logger = logging.getLogger("smartinstantindex")
    if os.path.exists("logging.conf"):
        logging.config.fileConfig("logging.conf")
    else:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    return logger


APP_LOGGER = create_logger()


DEFAULT_SKIP_EXTENSIONS = [
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg",
    ".pdf", ".mp4", ".zip",
]


def normalize_config(config):
    """Normalize config to multi-site format, filling in defaults per site."""
    # Legacy format: bare sitemap_url at root
    if "sitemap_url" in config:
        config = {
            "sites": [
                {
                    "name": "default",
                    "sitemap_url": config["sitemap_url"],
                    "credentials": config.get("credentials", "credentials.json"),
                    "urls_file": config.get("urls_file", "urls.json"),
                }
            ]
        }

    for site in config.get("sites", []):
        creds = site.get("credentials", "credentials.json")
        if isinstance(creds, str):
            creds = [creds]
        site["credentials"] = creds
        site.setdefault("urls_file", f"urls_{site['name']}.json")
        site.setdefault("track_lastmod", False)
        site.setdefault("skip_extensions", DEFAULT_SKIP_EXTENSIONS)
        site.setdefault("exclude_patterns", [])
        site.setdefault("include_patterns", [])
        site.setdefault("site_url", "")   # GSC property identifier; empty = GSC disabled
        site.setdefault("auto_reindex_enabled", False)
        site.setdefault("auto_reindex_days", 30)

    return config


VALID_REINDEX_DAYS = [10, 20, 30, 45, 60]


def migrate_urls(data):
    """Convert legacy {url: bool} format to {url: {"indexed": bool, "lastmod": None}}.

    Ensures gsc_indexed defaults to False so smart-reindex selection works on legacy entries.
    """
    migrated = {}
    for url, value in data.items():
        if isinstance(value, bool):
            entry = {"indexed": value, "lastmod": None}
        else:
            entry = dict(value)
        entry.setdefault("gsc_indexed", False)
        migrated[url] = entry
    return migrated


def select_stale_indexed_urls(urls, days_threshold, now=None):
    """Return URLs that were submitted to the Indexing API more than `days_threshold`
    days ago but are still not confirmed as indexed in Google Search Console.

    `urls` is the per-URL state dict: ``{url: {"indexed": bool, "gsc_indexed": bool,
    "indexed_at": str | datetime | None, ...}}``. The function is pure (does not
    mutate the input) and is shared by the desktop (JSON state) and cloud (rows
    serialized from Supabase).
    """
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    stale = []
    for url, entry in urls.items():
        if not isinstance(entry, dict):
            continue
        if not entry.get("indexed"):
            continue
        if entry.get("gsc_indexed"):
            continue
        raw = entry.get("indexed_at")
        if not raw:
            continue
        ts = raw
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                continue
        if isinstance(ts, datetime):
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        else:
            continue
        age_days = (now - ts).total_seconds() / 86400.0
        if age_days > days_threshold:
            stale.append(url)
    return stale


def _matches(pattern, url):
    """Match a pattern against a URL.

    Accepts both plain substrings and regular expressions.
    JavaScript-style delimiters (/pattern/) are stripped automatically.
    If the pattern contains regex metacharacters it is compiled and searched;
    otherwise a simple substring check is used.
    """
    # Strip JS-style regex delimiters: /pattern/ or /pattern/flags
    if pattern.startswith("/") and pattern.rfind("/", 1) > 0:
        end = pattern.rfind("/", 1)
        pattern = pattern[1:end]  # discard delimiters and any flags

    _REGEX_CHARS = set(r"^$*+?{}[]|()")
    if any(c in pattern for c in _REGEX_CHARS):
        try:
            return bool(re.search(pattern, url))
        except re.error:
            return pattern in url  # fall back to substring on invalid regex
    return pattern in url


def filter_urls(urls, site_config):
    """Filter URLs by extension, exclude_patterns, and include_patterns.

    Patterns support both plain substrings and regular expressions.
    """
    skip_extensions = [e.lower() for e in site_config.get("skip_extensions", DEFAULT_SKIP_EXTENSIONS)]
    exclude_patterns = site_config.get("exclude_patterns", [])
    include_patterns = site_config.get("include_patterns", [])

    result = {}
    for url, lastmod in urls.items():
        # Filter by extension
        url_lower = url.lower()
        if any(url_lower.endswith(ext) for ext in skip_extensions):
            continue

        # Filter by exclude_patterns (exclusion wins)
        if any(_matches(pattern, url) for pattern in exclude_patterns):
            continue

        # Filter by include_patterns (whitelist — only active if non-empty)
        if include_patterns and not any(_matches(pattern, url) for pattern in include_patterns):
            continue

        result[url] = lastmod

    return result


def update_quota(credentials_file):
    """Increment the daily quota counter by 1 for the given credentials file."""
    update_quota_batch(credentials_file, 1)


def update_quota_batch(credentials_file, count):
    """Increment the daily quota counter by count in a single disk write."""
    quota_path = "quota.json"
    quota = load_json(quota_path)
    today = str(date.today())

    entry = quota.get(credentials_file)
    if entry and entry.get("date") == today:
        entry["used"] += count
    else:
        quota[credentials_file] = {"date": today, "used": count}

    with open(quota_path, "w") as f:
        json.dump(quota, f, indent=4)


QUOTA_LIMIT = 200


def get_quota_remaining(credentials_file):
    """Return how many URL submissions remain today for a given credentials file."""
    quota = load_json("quota.json")
    entry = quota.get(credentials_file, {})
    used = entry.get("used", 0) if entry.get("date") == str(date.today()) else 0
    return max(0, QUOTA_LIMIT - used)


def build_indexing_plan(credentials_list):
    """Return [(creds_file, remaining)] for credentials with quota > 0 today."""
    return [
        (creds, get_quota_remaining(creds))
        for creds in credentials_list
        if get_quota_remaining(creds) > 0
    ]
