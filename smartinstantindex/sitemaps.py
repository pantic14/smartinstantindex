import requests
from bs4 import BeautifulSoup


def fetch_urls_from_sitemap(sitemap_url):
    response = requests.get(sitemap_url)
    if response.status_code == 200:
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
