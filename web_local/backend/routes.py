"""
SmartInstantIndex — Local Web Backend
FastAPI app: serves the Astro static build and exposes the API.
"""
import asyncio
import json
import os
import sys
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DATA_DIR = Path(os.environ.get("SMARTINDEX_DATA_DIR", Path(__file__).parent.parent.parent))
STATIC_DIR = Path(os.environ.get("SMARTINDEX_STATIC_DIR", Path(__file__).parent.parent / "frontend" / "dist"))

sys.path.insert(0, str(DATA_DIR))  # so we can import smartinstantindex.*

from smartinstantindex.utils import (
    load_json, save_urls_to_file, normalize_config,
    migrate_urls, filter_urls, build_indexing_plan,
    update_quota_batch, get_quota_remaining, QUOTA_LIMIT,
    DEFAULT_SKIP_EXTENSIONS,
)
from smartinstantindex.sitemaps import fetch_urls_from_sitemap_recursive
from smartinstantindex.indexing import index_url
from smartinstantindex.searchconsole import fetch_indexed_pages

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def config_path() -> Path:
    return DATA_DIR / "config.json"


def get_config() -> dict:
    raw = load_json(str(config_path()))
    return normalize_config(raw) if raw else {"sites": []}


def save_config(config: dict) -> None:
    with open(config_path(), "w") as f:
        json.dump(config, f, indent=4)


def get_site(name: str) -> dict:
    config = get_config()
    for site in config.get("sites", []):
        if site["name"] == name:
            return site
    raise HTTPException(status_code=404, detail=f"Site '{name}' not found")


def urls_path(site: dict) -> Path:
    return DATA_DIR / site["urls_file"]


def load_urls(site: dict) -> dict:
    return migrate_urls(load_json(str(urls_path(site))))


def creds_path(filename: str) -> Path:
    return DATA_DIR / filename


def quota_for_site(site: dict) -> list[dict]:
    result = []
    for creds_file in site.get("credentials", []):
        full = str(creds_path(creds_file))
        quota_data = load_json(str(DATA_DIR / "quota.json"))
        entry = quota_data.get(creds_file, {})
        used = entry.get("used", 0) if entry.get("date") == str(date.today()) else 0
        result.append({
            "credentials_file": creds_file,
            "credentials_name": creds_file.replace(".json", ""),
            "used": used,
            "limit": QUOTA_LIMIT,
            "remaining": max(0, QUOTA_LIMIT - used),
        })
    return result


def site_stats(site: dict) -> dict:
    urls = load_urls(site)
    visible = filter_urls({url: data.get("lastmod") for url, data in urls.items()}, site)
    total = len(visible)
    indexed = sum(1 for url, u in urls.items() if url in visible and u.get("indexed"))
    gsc_indexed = sum(1 for url, u in urls.items() if url in visible and u.get("sc_synced_at"))
    pending = total - indexed
    return {
        "name": site["name"],
        "sitemap_url": site["sitemap_url"],
        "site_url": site.get("site_url", ""),
        "track_lastmod": site.get("track_lastmod", False),
        "schedule_enabled": site.get("schedule_enabled", False),
        "schedule_hour": site.get("schedule_hour", 8),
        "skip_extensions": site.get("skip_extensions", DEFAULT_SKIP_EXTENSIONS),
        "exclude_patterns": site.get("exclude_patterns", []),
        "include_patterns": site.get("include_patterns", []),
        "credentials": site.get("credentials", []),
        "urls_total": total,
        "urls_indexed": indexed,
        "urls_gsc_indexed": gsc_indexed,
        "urls_pending": pending,
        "quota": quota_for_site(site),
    }


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="SmartInstantIndex Local")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:7842", "http://127.0.0.1:7842"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.get("/api/sites")
def list_sites():
    config = get_config()
    return [site_stats(s) for s in config.get("sites", [])]


@app.get("/api/sites/{name}/stats")
def get_site_stats(name: str):
    site = get_site(name)
    return site_stats(site)


# --- URL listing ---

@app.get("/api/sites/{name}/urls")
def list_urls(name: str, filter: str = "all", page: int = 1, page_size: int = 100, search: str = ""):
    site = get_site(name)
    urls = load_urls(site)

    # Apply site filters so excluded URLs are hidden from view
    # (they stay in storage to preserve their indexed state)
    visible = filter_urls({url: data.get("lastmod") for url, data in urls.items()}, site)

    items = []
    for url, data in urls.items():
        if url not in visible:
            continue
        indexed = data.get("indexed", False)
        gsc_indexed = data.get("gsc_indexed", False)
        if filter == "pending" and indexed:
            continue
        if filter == "indexed" and not indexed:
            continue
        if filter == "gsc_indexed" and not gsc_indexed:
            continue
        items.append({
            "url": url,
            "indexed": indexed,
            "indexed_at": data.get("indexed_at"),
            "lastmod": data.get("lastmod"),
            "sc_synced_at": data.get("sc_synced_at"),
        })

    if search:
        items = [i for i in items if search.lower() in i["url"].lower()]

    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    return {"data": items[start:end], "total": total, "page": page, "page_size": page_size}


# --- Site CRUD ---

class SiteCreate(BaseModel):
    name: str
    sitemap_url: str
    site_url: str = ""
    track_lastmod: bool = False
    credentials: list[str] = []
    skip_extensions: list[str] = DEFAULT_SKIP_EXTENSIONS
    exclude_patterns: list[str] = []
    include_patterns: list[str] = []


@app.post("/api/sites")
def create_site(body: SiteCreate):
    config = get_config()
    names = [s["name"] for s in config.get("sites", [])]
    if body.name in names:
        raise HTTPException(status_code=409, detail="Site name already exists")

    site = {
        "name": body.name,
        "sitemap_url": body.sitemap_url,
        "site_url": body.site_url,
        "track_lastmod": body.track_lastmod,
        "credentials": body.credentials,
        "urls_file": f"urls_{body.name}.json",
        "skip_extensions": body.skip_extensions,
        "exclude_patterns": body.exclude_patterns,
        "include_patterns": body.include_patterns,
    }
    config.setdefault("sites", []).append(site)
    save_config(config)
    return site_stats(site)


class SiteUpdate(BaseModel):
    sitemap_url: Optional[str] = None
    site_url: Optional[str] = None
    track_lastmod: Optional[bool] = None
    credentials: Optional[list[str]] = None
    skip_extensions: Optional[list[str]] = None
    exclude_patterns: Optional[list[str]] = None
    include_patterns: Optional[list[str]] = None


@app.put("/api/sites/{name}")
def update_site(name: str, body: SiteUpdate):
    config = get_config()
    for site in config.get("sites", []):
        if site["name"] == name:
            for field, val in body.model_dump(exclude_none=True).items():
                site[field] = val
            save_config(config)
            return site_stats(site)
    raise HTTPException(status_code=404, detail="Site not found")


@app.delete("/api/sites/{name}")
def delete_site(name: str):
    config = get_config()
    sites = config.get("sites", [])
    config["sites"] = [s for s in sites if s["name"] != name]
    save_config(config)
    return {"ok": True}


# --- Actions ---

@app.post("/api/sites/{name}/fetch-urls")
def fetch_urls(name: str):
    site = get_site(name)
    raw = fetch_urls_from_sitemap_recursive(site["sitemap_url"])
    filtered = filter_urls(raw, site)
    existing = load_urls(site)
    today = str(date.today())

    new_count = 0
    del_count = 0
    reset_count = 0

    # Add new URLs
    for url, lastmod in filtered.items():
        if url not in existing:
            existing[url] = {"indexed": False, "lastmod": lastmod}
            new_count += 1
        elif site.get("track_lastmod") and lastmod and existing[url].get("lastmod") != lastmod:
            existing[url]["lastmod"] = lastmod
            existing[url]["indexed"] = False
            existing[url].pop("indexed_at", None)
            reset_count += 1

    # Remove URLs deleted from the sitemap (not just filtered out by patterns)
    for url in list(existing.keys()):
        if url not in raw:
            del existing[url]
            del_count += 1

    save_urls_to_file(existing, str(urls_path(site)))
    return {
        "found": len(filtered),
        "added": new_count,
        "removed": del_count,
        "reset": reset_count,
    }


@app.post("/api/sites/{name}/mark-indexed")
def mark_indexed(name: str, body: dict):
    site = get_site(name)
    urls_list = body.get("urls", [])
    existing = load_urls(site)
    today = str(date.today())
    for url in urls_list:
        if url in existing:
            existing[url]["indexed"] = True
            existing[url]["indexed_at"] = today
    save_urls_to_file(existing, str(urls_path(site)))
    return {"ok": True}


@app.post("/api/sites/{name}/reset")
def reset_urls(name: str, body: dict):
    site = get_site(name)
    urls_list = body.get("urls", [])  # empty = reset all
    existing = load_urls(site)
    targets = urls_list if urls_list else list(existing.keys())
    for url in targets:
        if url in existing:
            existing[url]["indexed"] = False
            existing[url].pop("indexed_at", None)
    save_urls_to_file(existing, str(urls_path(site)))
    return {"ok": True}


# --- SSE: Run Selected URLs ---

@app.post("/api/sites/{name}/run/selected/stream")
def run_selected_stream(name: str, body: dict):
    site = get_site(name)
    urls_to_index = body.get("urls", [])
    if not urls_to_index:
        raise HTTPException(status_code=400, detail="No URLs provided")

    def generate():
        def send(event: dict) -> str:
            return f"data: {json.dumps(event)}\n\n"

        yield send({"type": "connected"})

        try:
            existing = load_urls(site)
            today = str(date.today())

            plan = build_indexing_plan(site["credentials"])
            total_capacity = sum(cap for _, cap in plan)
            # Only include URLs that exist in our data store
            pending_urls = [u for u in urls_to_index if u in existing][:total_capacity]

            yield send({"type": "plan", "pending": len(urls_to_index), "capacity": total_capacity})

            if not plan or not pending_urls:
                yield send({"type": "done", "indexed": 0, "pending": len(urls_to_index)})
                return

            global_i = 0
            indexed_tally: dict[str, int] = {}
            url_cursor = 0

            for creds_file, capacity in plan:
                batch = pending_urls[url_cursor: url_cursor + capacity]
                if not batch:
                    break
                creds_full = str(creds_path(creds_file))
                batch_indexed = 0

                for url in batch:
                    try:
                        index_url(url, creds_full, global_i + 1)
                        existing[url]["indexed"] = True
                        existing[url]["indexed_at"] = today
                        global_i += 1
                        batch_indexed += 1
                        indexed_tally[creds_file] = indexed_tally.get(creds_file, 0) + 1
                        yield send({"type": "indexed", "url": url, "done": global_i, "total": len(pending_urls)})
                    except Exception as e:
                        msg = str(e)
                        if "429" in msg or "quota" in msg.lower():
                            yield send({"type": "quota_exhausted", "message": f"Quota exhausted for {creds_file}"})
                            break
                        else:
                            yield send({"type": "error", "message": msg})
                            save_urls_to_file(existing, str(urls_path(site)))
                            return

                url_cursor += batch_indexed

            save_urls_to_file(existing, str(urls_path(site)))
            for creds_file, count in indexed_tally.items():
                if count:
                    update_quota_batch(creds_file, count)

            yield send({"type": "done", "indexed": global_i, "pending": len(urls_to_index) - global_i})

        except Exception as e:
            yield send({"type": "error", "message": str(e)})

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


# --- SSE: Run Indexing ---

@app.get("/api/sites/{name}/run/stream")
def run_stream(name: str):
    site = get_site(name)

    def generate():
        def send(event: dict) -> str:
            return f"data: {json.dumps(event)}\n\n"

        yield send({"type": "connected"})

        try:
            # Fetch sitemap
            yield send({"type": "status", "message": "Fetching sitemap..."})
            raw = fetch_urls_from_sitemap_recursive(site["sitemap_url"])
            filtered = filter_urls(raw, site)
            yield send({"type": "urls_found", "count": len(filtered)})

            # Sync URLs
            existing = load_urls(site)
            today = str(date.today())
            for url, lastmod in filtered.items():
                if url not in existing:
                    existing[url] = {"indexed": False, "lastmod": lastmod}
                elif site.get("track_lastmod") and lastmod and existing[url].get("lastmod") != lastmod:
                    existing[url]["lastmod"] = lastmod
                    existing[url]["indexed"] = False
                    existing[url].pop("indexed_at", None)
            for url in list(existing.keys()):
                if url not in raw:
                    del existing[url]

            # Build plan
            plan = build_indexing_plan(site["credentials"])
            pending_urls = [u for u, d in existing.items() if not d.get("indexed")]
            total_capacity = sum(cap for _, cap in plan)
            total_to_index = min(len(pending_urls), total_capacity)

            yield send({"type": "plan", "pending": len(pending_urls), "capacity": total_capacity})

            if not plan:
                yield send({"type": "done", "indexed": 0, "pending": len(pending_urls)})
                return

            global_i = 0
            indexed_tally: dict[str, int] = {}

            for creds_file, capacity in plan:
                if not pending_urls:
                    break
                batch = pending_urls[:capacity]
                pending_urls = pending_urls[capacity:]
                creds_full = str(creds_path(creds_file))

                for url in batch:
                    try:
                        index_url(url, creds_full, global_i + 1)
                        existing[url]["indexed"] = True
                        existing[url]["indexed_at"] = today
                        global_i += 1
                        indexed_tally[creds_file] = indexed_tally.get(creds_file, 0) + 1
                        yield send({"type": "indexed", "url": url, "done": global_i, "total": total_to_index})
                    except Exception as e:
                        msg = str(e)
                        if "429" in msg or "quota" in msg.lower():
                            yield send({"type": "quota_exhausted", "message": f"Quota exhausted for {creds_file}"})
                            break
                        else:
                            yield send({"type": "error", "message": msg})
                            save_urls_to_file(existing, str(urls_path(site)))
                            return

            save_urls_to_file(existing, str(urls_path(site)))
            for creds_file, count in indexed_tally.items():
                if count:
                    update_quota_batch(creds_file, count)

            final_pending = sum(1 for d in existing.values() if not d.get("indexed"))
            yield send({"type": "done", "indexed": global_i, "pending": final_pending})

        except Exception as e:
            yield send({"type": "error", "message": str(e)})

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


# --- SSE: Sync GSC ---

@app.get("/api/sites/{name}/sync-gsc/stream")
def sync_gsc_stream(name: str):
    site = get_site(name)

    def generate():
        def send(event: dict) -> str:
            return f"data: {json.dumps(event)}\n\n"

        if not site.get("site_url"):
            yield send({"type": "error", "message": "No Google Search Console property configured for this site."})
            return
        if not site.get("credentials"):
            yield send({"type": "error", "message": "No credentials configured for this site."})
            return

        yield send({"type": "status", "message": "Connecting to Google Search Console..."})
        try:
            creds_file = site["credentials"][0]
            gsc_pages = fetch_indexed_pages(site["site_url"], str(creds_path(creds_file)))
            yield send({"type": "status", "message": f"Found {len(gsc_pages)} indexed pages in GSC."})

            # Normalize both sides: strip trailing slash for comparison
            gsc_normalized = {u.rstrip("/"): u for u in gsc_pages}

            existing = load_urls(site)
            today = str(date.today())
            synced = 0
            for url in existing:
                if url.rstrip("/") in gsc_normalized:
                    existing[url]["sc_synced_at"] = today
                    synced += 1
                    if not existing[url].get("indexed"):
                        existing[url]["indexed"] = True
                        existing[url]["indexed_at"] = today

            save_urls_to_file(existing, str(urls_path(site)))
            yield send({"type": "done", "synced": synced, "total": len(gsc_pages)})
        except Exception as e:
            yield send({"type": "error", "message": str(e)})

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


# --- Credentials ---

@app.get("/api/credentials")
def list_credentials():
    """List all .json files in DATA_DIR that look like service account credentials."""
    creds = []
    for f in DATA_DIR.iterdir():
        if f.suffix == ".json" and f.name not in ("config.json", "quota.json"):
            try:
                data = json.loads(f.read_text())
                if "type" in data and data.get("type") == "service_account":
                    creds.append({
                        "filename": f.name,
                        "client_email": data.get("client_email", ""),
                        "project_id": data.get("project_id", ""),
                    })
            except Exception:
                pass
    return creds


@app.post("/api/credentials/upload")
async def upload_credential(file: UploadFile = File(...)):
    content = await file.read()
    try:
        data = json.loads(content)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON file")
    if data.get("type") != "service_account":
        raise HTTPException(status_code=400, detail="Not a valid Google service account JSON")

    dest = DATA_DIR / file.filename
    dest.write_bytes(content)
    return {
        "filename": file.filename,
        "client_email": data.get("client_email", ""),
        "project_id": data.get("project_id", ""),
    }


@app.delete("/api/credentials/{filename}")
def delete_credential(filename: str):
    target = DATA_DIR / filename
    if not target.exists():
        raise HTTPException(status_code=404, detail="File not found")
    target.unlink()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Serve Astro static build (must be last)
# ---------------------------------------------------------------------------

if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
else:
    @app.get("/")
    def no_frontend():
        return JSONResponse(
            {"error": "Frontend not built. Run: cd web_local/frontend && npm run build"},
            status_code=503,
        )
