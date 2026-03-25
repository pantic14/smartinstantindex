from smartinstantindex.sitemaps import fetch_urls_from_sitemap_recursive
from smartinstantindex.utils import (
    load_json, save_urls_to_file, APP_LOGGER,
    normalize_config, migrate_urls, filter_urls, update_quota,
)
from smartinstantindex.indexing import index_url

config = load_json("config.json")
sites = normalize_config(config)["sites"]

for site in sites:
    APP_LOGGER.info(f"Processing site: {site['name']} — {site['sitemap_url']}")

    # Fetch and filter URLs from sitemap
    sitemap_urls = fetch_urls_from_sitemap_recursive(site["sitemap_url"])
    sitemap_urls = filter_urls(sitemap_urls, site)
    APP_LOGGER.info(f"Total URLs after filtering: {len(sitemap_urls)}")

    # Load and migrate existing state
    existing_urls = migrate_urls(load_json(site["urls_file"]))

    # Add new URLs
    NEW_URLS = 0
    for url in sitemap_urls:
        if url not in existing_urls:
            NEW_URLS += 1
            existing_urls[url] = {"indexed": False, "lastmod": sitemap_urls[url]}

    # Remove deleted URLs
    DELETED_URLS = 0
    for url in list(existing_urls):
        if url not in sitemap_urls:
            DELETED_URLS += 1
            del existing_urls[url]

    # Reset URLs whose lastmod changed
    if site["track_lastmod"]:
        for url, entry in existing_urls.items():
            new_lastmod = sitemap_urls.get(url)
            if new_lastmod and new_lastmod != entry.get("lastmod"):
                APP_LOGGER.info(
                    f"lastmod changed for {url}: {entry.get('lastmod')} → {new_lastmod}"
                )
                entry["indexed"] = False
                entry["lastmod"] = new_lastmod

    save_urls_to_file(existing_urls, site["urls_file"])

    if NEW_URLS:
        APP_LOGGER.info(f"New URLs added: {NEW_URLS}")
    if DELETED_URLS:
        APP_LOGGER.info(f"Deleted URLs: {DELETED_URLS}")

    # Index pending URLs (up to 200)
    urls_to_index = [url for url, entry in existing_urls.items() if not entry["indexed"]][:200]
    APP_LOGGER.info(f"Total URLs to index: {len(urls_to_index)}")

    for i, url in enumerate(urls_to_index, 1):
        try:
            result = index_url(url, site["credentials"], i)
            if result:
                existing_urls[url]["indexed"] = True
                update_quota(site["credentials"])

        except Exception as e:
            existing_urls[url]["indexed"] = False
            APP_LOGGER.warning(f"Error indexing {url}: {e}")
            break

    save_urls_to_file(existing_urls, site["urls_file"])
