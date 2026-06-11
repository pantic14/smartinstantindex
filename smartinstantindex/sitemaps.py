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


def fetch_urls_from_sitemap_recursive(sitemap_url, visited_sitemaps=None, use_scrapingant=True, _collected=None):
    """Recursively collect ``{url: lastmod}`` from a sitemap (handles sitemap indexes).

    The accumulator (``_collected``) and the visited set are created fresh on the
    top-level call and threaded down through the recursion, so the function is
    fully reentrant: concurrent calls for different sites never share state.
    Do not pass ``_collected`` from outside; it is an internal recursion argument.
    """
    if visited_sitemaps is None:
        visited_sitemaps = set()
    if _collected is None:
        _collected = {}

    visited_sitemaps.add(sitemap_url)
    urls = fetch_urls_from_sitemap(sitemap_url, use_scrapingant=use_scrapingant)

    for url, lastmod in urls.items():
        if url.endswith(".xml"):
            if url not in visited_sitemaps:
                fetch_urls_from_sitemap_recursive(
                    url, visited_sitemaps, use_scrapingant=use_scrapingant, _collected=_collected
                )
        else:
            _collected[url] = lastmod

    return _collected
