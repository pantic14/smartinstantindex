import os
import urllib.parse
from curl_cffi import requests
from bs4 import BeautifulSoup


_IMPERSONATE_TARGETS = (
    "chrome136", "chrome131", "chrome124", "chrome120", "chrome110",
    "firefox135", "safari184",
)


def _is_xml_response(text: str) -> bool:
    t = text.lstrip()
    return t.startswith("<?xml") or t.startswith("<urlset") or t.startswith("<sitemapindex")


def _fetch_via_scrapingant(sitemap_url: str) -> str | None:
    api_key = os.environ.get("SCRAPINGANT_API_KEY")
    if not api_key:
        return None
    params = {"url": sitemap_url, "x-api-key": api_key, "browser": "true", "return_page_source": "true"}
    endpoint = "https://api.scrapingant.com/v2/general?" + urllib.parse.urlencode(params)
    try:
        r = requests.get(endpoint, timeout=30)
        if r.status_code == 200 and _is_xml_response(r.text):
            return r.text
    except Exception:
        pass
    return None


def fetch_urls_from_sitemap(sitemap_url, use_scrapingant=True):
    content = None
    for target in _IMPERSONATE_TARGETS:
        try:
            r = requests.get(sitemap_url, impersonate=target, timeout=20)
            if r.status_code == 200 and _is_xml_response(r.text):
                content = r.text
                break
        except Exception:
            continue

    if content is None and use_scrapingant:
        content = _fetch_via_scrapingant(sitemap_url)

    if content:
        soup = BeautifulSoup(content, features="xml")
        urls = {}
        for url_tag in soup.find_all("url"):
            loc = url_tag.find("loc")
            if loc:
                lastmod = url_tag.find("lastmod")
                urls[loc.text] = lastmod.text if lastmod else None
        for loc in soup.find_all("loc"):
            if loc.text not in urls:
                urls[loc.text] = None
        return urls
    else:
        print(f"Failed to fetch sitemap: {sitemap_url}")
        return {}


ALL_URLS = {}


def fetch_urls_from_sitemap_recursive(sitemap_url, visited_sitemaps=None, use_scrapingant=True):
    global ALL_URLS
    if visited_sitemaps is None:
        visited_sitemaps = set()
        ALL_URLS = {}

    visited_sitemaps.add(sitemap_url)
    urls = fetch_urls_from_sitemap(sitemap_url, use_scrapingant=use_scrapingant)

    for url, lastmod in urls.items():
        if not url.endswith(".xml"):
            ALL_URLS[url] = lastmod

        if url.endswith(".xml") and url not in visited_sitemaps:
            fetch_urls_from_sitemap_recursive(url, visited_sitemaps, use_scrapingant=use_scrapingant)

    return ALL_URLS
