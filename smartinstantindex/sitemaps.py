from curl_cffi import requests
from bs4 import BeautifulSoup


_IMPERSONATE_TARGETS = (
    "chrome136", "chrome131", "chrome124", "chrome120", "chrome110",
    "firefox135", "safari184",
)


def _is_xml_response(text: str) -> bool:
    t = text.lstrip()
    return t.startswith("<?xml") or t.startswith("<urlset") or t.startswith("<sitemapindex")


def fetch_urls_from_sitemap(sitemap_url):
    response = None
    for target in _IMPERSONATE_TARGETS:
        try:
            r = requests.get(sitemap_url, impersonate=target, timeout=20)
            if r.status_code == 200 and _is_xml_response(r.text):
                response = r
                break
        except Exception:
            continue
    if response is not None:
        soup = BeautifulSoup(response.text, features="xml")
        urls = {}
        for url_tag in soup.find_all("url"):
            loc = url_tag.find("loc")
            if loc:
                lastmod = url_tag.find("lastmod")
                urls[loc.text] = lastmod.text if lastmod else None
        # Also handle sitemap index entries (sitemaploc entries have no <url> wrapper)
        for loc in soup.find_all("loc"):
            if loc.text not in urls:
                urls[loc.text] = None
        return urls
    else:
        print(f"Failed to fetch sitemap: {sitemap_url}")
        return {}


ALL_URLS = {}


def fetch_urls_from_sitemap_recursive(sitemap_url, visited_sitemaps=None):
    global ALL_URLS
    if visited_sitemaps is None:
        visited_sitemaps = set()
        ALL_URLS = {}

    visited_sitemaps.add(sitemap_url)
    urls = fetch_urls_from_sitemap(sitemap_url)

    for url, lastmod in urls.items():
        if not url.endswith(".xml"):
            ALL_URLS[url] = lastmod

        if url.endswith(".xml") and url not in visited_sitemaps:
            fetch_urls_from_sitemap_recursive(url, visited_sitemaps)

    return ALL_URLS
