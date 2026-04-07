from smartinstantindex.sitemaps import fetch_urls_from_sitemap_recursive
from smartinstantindex.utils import (
    load_json, save_urls_to_file, APP_LOGGER,
    normalize_config, migrate_urls, filter_urls, update_quota_batch, build_indexing_plan,
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

    # Index pending URLs (rotating across credentials when quota is exhausted)
    plan = build_indexing_plan(site["credentials"])
    total_capacity = sum(cap for _, cap in plan)
    pending_urls = [url for url, entry in existing_urls.items() if not entry["indexed"]]
    urls_to_index = pending_urls[:total_capacity]
    APP_LOGGER.info(f"Total URLs to index: {len(urls_to_index)} (capacity: {total_capacity})")

    indexed_tally = {}
    url_cursor = 0
    global_index = 1

    for creds_file, capacity in plan:
        batch = urls_to_index[url_cursor: url_cursor + capacity]
        if not batch:
            break
        batch_indexed = 0
        quota_exhausted = False
        for url in batch:
            try:
                result = index_url(url, creds_file, global_index)
                if result:
                    existing_urls[url]["indexed"] = True
                    batch_indexed += 1
                    global_index += 1
            except Exception as e:
                APP_LOGGER.warning(f"Error indexing {url}: {e}")
                save_urls_to_file(existing_urls, site["urls_file"])
                if batch_indexed:
                    update_quota_batch(creds_file, batch_indexed)
                if "Rate limit" in str(e) or "429" in str(e):
                    APP_LOGGER.info(f"Quota exhausted for {creds_file}, switching to next credential.")
                    quota_exhausted = True
                    break
                raise
        url_cursor += batch_indexed  # advance by actually indexed count so next credential retries from here
        indexed_tally[creds_file] = batch_indexed
        if quota_exhausted:
            continue

    save_urls_to_file(existing_urls, site["urls_file"])
    for creds_file, count in indexed_tally.items():
        if count:
            update_quota_batch(creds_file, count)
            APP_LOGGER.info(f"  {creds_file}: {count} URLs indexed")
