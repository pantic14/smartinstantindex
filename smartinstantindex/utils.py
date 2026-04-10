import json
import logging
import logging.config
import os
import re
from datetime import date


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

    return config


def migrate_urls(data):
    """Convert legacy {url: bool} format to {url: {"indexed": bool, "lastmod": None}}."""
    migrated = {}
    for url, value in data.items():
        if isinstance(value, bool):
            migrated[url] = {"indexed": value, "lastmod": None}
        else:
            migrated[url] = value
    return migrated


def _matches(pattern, url):
    """Match a pattern against a URL.

    If the pattern looks like a regex (contains regex metacharacters beyond
    plain path text), it is compiled and searched; otherwise a simple substring
    check is used so existing plain-text patterns keep working.
    """
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
