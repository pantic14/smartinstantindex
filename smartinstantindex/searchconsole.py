import json
from datetime import date, timedelta
from urllib.parse import quote

import httplib2
from oauth2client.service_account import ServiceAccountCredentials

from smartinstantindex.utils import APP_LOGGER

# Requires "Google Search Console API" enabled in GCP project
# (separate from "Web Search Indexing API")
SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
BASE_URL = "https://www.googleapis.com/webmasters/v3/sites"


def _make_http(credentials_json: str):
    credentials = ServiceAccountCredentials.from_json_keyfile_name(
        credentials_json, scopes=SCOPES
    )
    return credentials.authorize(httplib2.Http())


def list_gsc_properties(credentials_json: str) -> list:
    """Return a list of GSC property URLs accessible by this service account.

    Useful for diagnosing which site_url value to configure.
    """
    http = _make_http(credentials_json)
    response, content = http.request(BASE_URL, method="GET")
    if response.status != 200:
        try:
            detail = json.loads(content).get("error", {}).get("message", content.decode()[:300])
        except Exception:
            detail = content.decode()[:300]
        raise Exception(f"Could not list GSC properties ({response.status}): {detail}")
    data = json.loads(content)
    return [entry["siteUrl"] for entry in data.get("siteEntry", [])]


def fetch_indexed_pages(site_url: str, credentials_json: str, months_back: int = 16) -> set:
    """Fetch all pages with Search Console impressions in the last N months.

    Pages with at least one impression are confirmed indexed by Google.
    Uses pagination — returns a set of all page URLs found.

    Requires the 'Google Search Console API' to be enabled in the GCP project.
    The service account must have Owner or Full User access to the GSC property.
    """
    http = _make_http(credentials_json)

    # URL prefix properties require a trailing slash; domain properties (sc-domain:) do not
    if site_url.startswith("http") and not site_url.endswith("/"):
        site_url = site_url + "/"

    end_date = str(date.today())
    start_date = str(date.today() - timedelta(days=months_back * 30))

    encoded_site = quote(site_url, safe="")
    endpoint = f"{BASE_URL}/{encoded_site}/searchAnalytics/query"

    all_pages = set()
    start_row = 0
    row_limit = 25000

    while True:
        body = json.dumps({
            "startDate": start_date,
            "endDate": end_date,
            "dimensions": ["page"],
            "rowLimit": row_limit,
            "startRow": start_row,
        })
        response, content = http.request(
            endpoint,
            method="POST",
            body=body,
            headers={"Content-Type": "application/json"},
        )

        if response.status == 403:
            try:
                detail = json.loads(content).get("error", {}).get("message", content.decode()[:300])
            except Exception:
                detail = content.decode()[:300]
            # Try to list available properties to help diagnose the mismatch
            available = []
            try:
                available = list_gsc_properties(credentials_json)
            except Exception:
                pass
            props_hint = (
                "\n\nProperties accessible to this service account:\n  " +
                "\n  ".join(available) if available else
                "\n\nCould not list properties — the 'Google Search Console API' may not be enabled in GCP."
            )
            raise Exception(
                f"Access denied (403): {detail}\n"
                f"Tried site URL: {site_url}"
                f"{props_hint}"
            )
        if response.status == 429:
            raise Exception("GSC rate limit reached. Please try again later.")
        if response.status != 200:
            try:
                detail = json.loads(content).get("error", {}).get("message", content.decode()[:200])
            except Exception:
                detail = content.decode()[:200]
            raise Exception(f"GSC API error {response.status}: {detail}")

        data = json.loads(content)
        rows = data.get("rows", [])
        if not rows:
            break

        for row in rows:
            all_pages.add(row["keys"][0])

        APP_LOGGER.info(f"GSC: fetched {len(rows)} pages (total: {len(all_pages)})")

        if len(rows) < row_limit:
            break
        start_row += row_limit

    return all_pages
