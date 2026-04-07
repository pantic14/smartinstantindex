import sys
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from datetime import date
import customtkinter as ctk

# Resolve data directory to the folder containing the executable (or script)
if getattr(sys, "frozen", False):
    DATA_DIR = os.path.dirname(sys.executable)
else:
    DATA_DIR = os.path.dirname(os.path.abspath(__file__))

def data_path(filename):
    return os.path.join(DATA_DIR, filename)

# Ensure relative paths (logging.conf, etc.) resolve to DATA_DIR
os.chdir(DATA_DIR)

from smartinstantindex.utils import (
    load_json, save_urls_to_file, normalize_config,
    migrate_urls, filter_urls, update_quota_batch, DEFAULT_SKIP_EXTENSIONS,
    build_indexing_plan,
)
from smartinstantindex.sitemaps import fetch_urls_from_sitemap_recursive
from smartinstantindex.indexing import index_url
from smartinstantindex.searchconsole import fetch_indexed_pages

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

CONFIG_FILE = data_path("config.json")
QUOTA_FILE = data_path("quota.json")

# ─── Config cache ─────────────────────────────────────────────────────────────
_config_cache = None

def get_config():
    global _config_cache
    if _config_cache is None:
        _config_cache = normalize_config(load_json(CONFIG_FILE))
    return _config_cache

def invalidate_config_cache():
    global _config_cache
    _config_cache = None

def save_config(config):
    save_urls_to_file(config, CONFIG_FILE)
    invalidate_config_cache()


# ─── Main App ────────────────────────────────────────────────────────────────

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("SmartInstantIndex")
        self.geometry("1100x700")
        self.minsize(900, 600)

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = Sidebar(self, self._show_screen)
        self.sidebar.grid(row=0, column=0, sticky="nsw")

        self.content = ctk.CTkFrame(self, corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        self.screens = {}
        self.current_screen = None
        self._show_screen("dashboard")

    def _show_screen(self, name):
        if self.current_screen:
            self.current_screen.grid_forget()

        if name not in self.screens:
            screen_cls = {
                "dashboard": DashboardScreen,
                "urls": URLsScreen,
                "sites": SitesScreen,
                "settings": SettingsScreen,
                "help": HelpScreen,
            }[name]
            self.screens[name] = screen_cls(self.content, self)

        self.current_screen = self.screens[name]
        self.current_screen.grid(row=0, column=0, sticky="nsew")
        self.current_screen.on_show()


# ─── Sidebar ─────────────────────────────────────────────────────────────────

class Sidebar(ctk.CTkFrame):
    BUTTONS = [
        ("dashboard", "Dashboard"),
        ("urls", "URLs"),
        ("sites", "Sites"),
        ("settings", "Settings"),
        ("help", "Help"),
    ]

    def __init__(self, parent, on_navigate):
        super().__init__(parent, width=180, corner_radius=0)
        self.on_navigate = on_navigate
        self.grid_rowconfigure(len(self.BUTTONS) + 1, weight=1)

        ctk.CTkLabel(self, text="SmartInstantIndex", font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, padx=20, pady=(20, 30)
        )

        for i, (name, label) in enumerate(self.BUTTONS, 1):
            ctk.CTkButton(
                self, text=label, width=140,
                command=lambda n=name: self.on_navigate(n)
            ).grid(row=i, column=0, padx=20, pady=6)


# ─── Dashboard ───────────────────────────────────────────────────────────────

class DashboardScreen(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, corner_radius=0)
        self.app = app
        self._running = False
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text="Dashboard", font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, padx=30, pady=(20, 10), sticky="w"
        )

        # Site selector
        sel_frame = ctk.CTkFrame(self)
        sel_frame.grid(row=1, column=0, padx=30, pady=5, sticky="w")
        ctk.CTkLabel(sel_frame, text="Site:").pack(side="left", padx=(0, 8))
        self.site_var = ctk.StringVar()
        self.site_dropdown = ctk.CTkOptionMenu(sel_frame, variable=self.site_var, width=250,
                                               command=lambda _: self._refresh_stats())
        self.site_dropdown.pack(side="left")

        # Stats
        stats_frame = ctk.CTkFrame(self)
        stats_frame.grid(row=2, column=0, padx=30, pady=10, sticky="ew")
        stats_frame.grid_columnconfigure((0, 1, 2), weight=1)
        self.stat_labels = {}
        for col, key in enumerate(["Total URLs", "Indexed", "Pending"]):
            f = ctk.CTkFrame(stats_frame)
            f.grid(row=0, column=col, padx=10, pady=10, sticky="ew")
            ctk.CTkLabel(f, text=key, font=ctk.CTkFont(size=12)).pack(pady=(8, 0))
            lbl = ctk.CTkLabel(f, text="—", font=ctk.CTkFont(size=22, weight="bold"))
            lbl.pack(pady=(0, 8))
            self.stat_labels[key] = lbl

        # Daily quota section (per-credential progress bars)
        quota_section = ctk.CTkFrame(self)
        quota_section.grid(row=3, column=0, padx=30, pady=(0, 5), sticky="ew")
        quota_section.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(quota_section, text="Daily Quota",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=0, column=0, padx=10, pady=(8, 4), sticky="w")
        self.quota_bars_frame = ctk.CTkFrame(quota_section, fg_color="transparent")
        self.quota_bars_frame.grid(row=1, column=0, padx=10, pady=(0, 8), sticky="ew")
        self.quota_bars_frame.grid_columnconfigure(1, weight=1)

        # Run button + progress
        action_frame = ctk.CTkFrame(self)
        action_frame.grid(row=4, column=0, padx=30, pady=5, sticky="ew")
        self.run_btn = ctk.CTkButton(action_frame, text="Run Indexing", command=self._run)
        self.run_btn.pack(side="left", padx=10, pady=10)
        self.progress = ctk.CTkProgressBar(action_frame)
        self.progress.pack(side="left", fill="x", expand=True, padx=10, pady=10)
        self.progress.set(0)

        # Log area
        ctk.CTkLabel(self, text="Log", font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=5, column=0, padx=30, pady=(10, 0), sticky="w"
        )
        self.grid_rowconfigure(6, weight=1)
        self.log_box = ctk.CTkTextbox(self, state="disabled")
        self.log_box.grid(row=6, column=0, padx=30, pady=(5, 20), sticky="nsew")

    def on_show(self):
        # Single config read for both methods
        config = get_config()
        self._refresh_sites(config)
        self._refresh_stats(config)

    def _refresh_sites(self, config=None):
        if config is None:
            config = get_config()
        names = [s["name"] for s in config.get("sites", [])]
        self.site_dropdown.configure(values=names)
        if names:
            if self.site_var.get() not in names:
                self.site_var.set(names[0])
        else:
            self.site_var.set("")

    def _refresh_stats(self, config=None):
        if config is None:
            config = get_config()
        site = next((s for s in config.get("sites", []) if s["name"] == self.site_var.get()), None)
        if not site:
            for lbl in self.stat_labels.values():
                lbl.configure(text="—")
            self._rebuild_quota_bars([])
            return

        urls = migrate_urls(load_json(data_path(site["urls_file"])))
        total = len(urls)
        indexed = sum(1 for e in urls.values() if e["indexed"])
        pending = total - indexed

        self.stat_labels["Total URLs"].configure(text=str(total))
        self.stat_labels["Indexed"].configure(text=str(indexed))
        self.stat_labels["Pending"].configure(text=str(pending))
        self._rebuild_quota_bars(site["credentials"])

    def _rebuild_quota_bars(self, credentials_list):
        for w in self.quota_bars_frame.winfo_children():
            w.destroy()
        today = str(date.today())
        quota_data = load_json(QUOTA_FILE)
        for row_idx, creds_file in enumerate(credentials_list):
            entry = quota_data.get(creds_file, {})
            used = entry.get("used", 0) if entry.get("date") == today else 0
            ctk.CTkLabel(self.quota_bars_frame, text=creds_file,
                         font=ctk.CTkFont(size=11), anchor="w").grid(
                row=row_idx, column=0, padx=(0, 8), pady=3, sticky="w")
            bar = ctk.CTkProgressBar(self.quota_bars_frame)
            bar.grid(row=row_idx, column=1, padx=(0, 8), pady=3, sticky="ew")
            bar.set(used / 200)
            ctk.CTkLabel(self.quota_bars_frame, text=f"{used}/200",
                         font=ctk.CTkFont(size=11), width=70, anchor="e").grid(
                row=row_idx, column=2, pady=3, sticky="e")

    def _log(self, msg):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _run(self):
        if self._running:
            return
        site_name = self.site_var.get()
        if not site_name:
            messagebox.showwarning("No site", "Select a site first.")
            return
        self._running = True
        self.run_btn.configure(state="disabled")
        self.progress.set(0)
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
        threading.Thread(target=self._run_indexing, args=(site_name,), daemon=True).start()

    def _run_indexing(self, site_name):
        try:
            config = get_config()
            site = next((s for s in config["sites"] if s["name"] == site_name), None)
            if not site:
                self._log(f"Site '{site_name}' not found.")
                return

            for creds_name in site["credentials"]:
                creds_path = data_path(creds_name)
                if not os.path.exists(creds_path):
                    self._log(f"ERROR: credentials file not found: {creds_path}")
                    return

            self._log(f"Fetching sitemap: {site['sitemap_url']}")
            try:
                sitemap_urls = fetch_urls_from_sitemap_recursive(site["sitemap_url"])
            except Exception as e:
                self._log(f"ERROR fetching sitemap: {e}")
                return

            sitemap_urls = filter_urls(sitemap_urls, site)
            self._log(f"URLs after filtering: {len(sitemap_urls)}")

            existing_urls = migrate_urls(load_json(data_path(site["urls_file"])))

            new_count = 0
            for url in sitemap_urls:
                if url not in existing_urls:
                    existing_urls[url] = {"indexed": False, "lastmod": sitemap_urls[url]}
                    new_count += 1

            del_count = 0
            for url in list(existing_urls):
                if url not in sitemap_urls:
                    del existing_urls[url]
                    del_count += 1

            if site["track_lastmod"]:
                for url, entry in existing_urls.items():
                    new_lastmod = sitemap_urls.get(url)
                    if new_lastmod and new_lastmod != entry.get("lastmod"):
                        self._log(f"lastmod changed: {url}")
                        entry["indexed"] = False
                        entry["lastmod"] = new_lastmod

            if new_count:
                self._log(f"New URLs: {new_count}")
            if del_count:
                self._log(f"Removed URLs: {del_count}")

            # Save state after diff (before indexing loop)
            save_urls_to_file(existing_urls, data_path(site["urls_file"]))

            plan = build_indexing_plan(site["credentials"])
            total_capacity = sum(cap for _, cap in plan)
            pending = [url for url, e in existing_urls.items() if not e["indexed"]]
            urls_to_index = pending[:total_capacity]
            plan_summary = ", ".join(f"{c}={cap}" for c, cap in plan)
            self._log(f"Pending to index: {len(urls_to_index)} (capacity: {total_capacity} — {plan_summary})")

            indexed_tally = {}
            url_cursor = 0
            global_i = 1
            total_to_index = len(urls_to_index)
            error_occurred = False

            for creds_name, capacity in plan:
                if error_occurred:
                    break
                batch = urls_to_index[url_cursor: url_cursor + capacity]
                if not batch:
                    break
                creds_path = data_path(creds_name)
                batch_indexed = 0
                for url in batch:
                    self.after(0, self.progress.set,
                               global_i / total_to_index if total_to_index else 1)
                    try:
                        result = index_url(url, creds_path, global_i)
                        if result:
                            existing_urls[url]["indexed"] = True
                            existing_urls[url]["indexed_at"] = str(date.today())
                            batch_indexed += 1
                            self._log(f"[{global_i}] OK: {url}")
                            global_i += 1
                    except Exception as e:
                        existing_urls[url]["indexed"] = False
                        self._log(f"[{global_i}] ERROR ({creds_name}): {e}")
                        if "Rate limit" in str(e) or "429" in str(e):
                            # Quota exhausted on this credential — save progress and try next
                            self._log(f"Quota exhausted for {creds_name}, switching to next credential.")
                        else:
                            error_occurred = True
                        break
                url_cursor += batch_indexed  # advance by actually indexed count so next credential retries from here
                indexed_tally[creds_name] = batch_indexed

            save_urls_to_file(existing_urls, data_path(site["urls_file"]))
            for creds_name, count in indexed_tally.items():
                if count:
                    update_quota_batch(creds_name, count)

            self._log("Done.")
            self.after(0, self._refresh_stats)

        finally:
            self._running = False
            self.after(0, lambda: self.run_btn.configure(state="normal"))
            self.after(0, lambda: self.progress.set(1))


# ─── URLs Screen ─────────────────────────────────────────────────────────────


class URLsScreen(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, corner_radius=0)
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(self, text="URLs", font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, padx=30, pady=(20, 10), sticky="w"
        )

        # Top controls
        top = ctk.CTkFrame(self)
        top.grid(row=1, column=0, padx=30, pady=5, sticky="ew")
        top.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(top, text="Site:").grid(row=0, column=0, padx=(10, 8))
        self.site_var = ctk.StringVar()
        self.site_dropdown = ctk.CTkOptionMenu(top, variable=self.site_var, width=200,
                                               command=lambda _: self._load_urls())
        self.site_dropdown.grid(row=0, column=1, padx=(0, 20))

        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._debounce_filter())
        ctk.CTkEntry(top, textvariable=self.search_var, placeholder_text="Search URLs…").grid(
            row=0, column=2, padx=(0, 10), sticky="ew"
        )

        # Buttons row — all packed left-to-right in a subframe
        btn_row = ctk.CTkFrame(top, fg_color="transparent")
        btn_row.grid(row=1, column=0, columnspan=3, padx=(10, 0), pady=(4, 0), sticky="w")

        self._fetch_btn = ctk.CTkButton(btn_row, text="Fetch URLs", width=100, command=self._fetch_urls)
        self._fetch_btn.pack(side="left", padx=(0, 6))
        ctk.CTkButton(btn_row, text="Mark indexed", width=110, command=self._mark_selected_indexed).pack(side="left", padx=(0, 6))
        ctk.CTkButton(btn_row, text="Reset selected", width=110, command=self._reset_selected).pack(side="left", padx=(0, 6))
        ctk.CTkButton(btn_row, text="Reset all", width=90, command=self._reset_all).pack(side="left", padx=(0, 6))
        self._gsc_btn = ctk.CTkButton(btn_row, text="Sync from GSC", width=120, command=self._check_gsc)
        self._gsc_btn.pack_forget()  # oculto hasta que el site tenga site_url configurado

        self._fetch_status = ctk.StringVar()
        ctk.CTkLabel(top, textvariable=self._fetch_status, font=ctk.CTkFont(size=11), text_color="#aaaaaa").grid(
            row=2, column=0, columnspan=3, padx=10, pady=(2, 6), sticky="w"
        )

        # Treeview with scrollbar
        tree_frame = tk.Frame(self)
        tree_frame.grid(row=2, column=0, padx=30, pady=(5, 20), sticky="nsew")
        tree_frame.grid_columnconfigure(0, weight=1)
        tree_frame.grid_rowconfigure(0, weight=1)

        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview",
            background="#2b2b2b", foreground="white",
            fieldbackground="#2b2b2b", rowheight=26, font=("", 11))
        style.configure("Treeview.Heading",
            background="#1f1f1f", foreground="white", font=("", 11, "bold"))
        style.map("Treeview", background=[("selected", "#1f538d")])

        self.tree = ttk.Treeview(
            tree_frame,
            columns=("url", "status", "lastmod", "submitted", "gsc"),
            show="headings",
            selectmode="extended",
        )
        self.tree.heading("url", text="URL")
        self.tree.heading("status", text="Status")
        self.tree.heading("lastmod", text="lastmod")
        self.tree.heading("submitted", text="Submitted")
        self.tree.heading("gsc", text="GSC Sync")
        self.tree.column("url", width=500, minwidth=200, stretch=False)
        self.tree.column("status", width=80, anchor="center", stretch=False)
        self.tree.column("lastmod", width=130, anchor="center", stretch=False)
        self.tree.column("submitted", width=130, anchor="center", stretch=False)
        self.tree.column("gsc", width=120, anchor="center", stretch=False)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        self.tree.tag_configure("indexed", foreground="#4caf50")
        self.tree.tag_configure("pending", foreground="#aaaaaa")

        self._all_urls = {}
        self._loaded_site = None   # tracks which site is currently loaded
        self._debounce_id = None   # for search debounce
        self._gsc_running = False

    def on_show(self):
        self._loaded_site = None  # always reload on tab switch
        config = get_config()
        names = [s["name"] for s in config.get("sites", [])]
        self.site_dropdown.configure(values=names)
        if names and self.site_var.get() not in names:
            self.site_var.set(names[0])
        self._load_urls()

    def _load_urls(self):
        current_site = self.site_var.get()
        if current_site == self._loaded_site:
            return  # already loaded — skip disk read
        config = get_config()
        site = next((s for s in config.get("sites", []) if s["name"] == current_site), None)
        self._all_urls = migrate_urls(load_json(data_path(site["urls_file"]))) if site else {}
        self._loaded_site = current_site
        has_gsc = bool(site and site.get("site_url"))
        if has_gsc:
            self._gsc_btn.pack(side="left", padx=(0, 6))
        else:
            self._gsc_btn.pack_forget()
        self._filter_table()

    def _debounce_filter(self):
        if self._debounce_id:
            self.after_cancel(self._debounce_id)
        self._debounce_id = self.after(200, self._filter_table)

    def _filter_table(self):
        self._debounce_id = None
        query = self.search_var.get().lower()
        self.tree.delete(*self.tree.get_children())
        for url, entry in self._all_urls.items():
            if query and query not in url.lower():
                continue
            status = "✓" if entry["indexed"] else "✗"
            tag = "indexed" if entry["indexed"] else "pending"
            gsc_synced = "✓" if entry.get("sc_synced_at") else "—"
            self.tree.insert("", "end", iid=url, values=(
                url, status,
                entry.get("lastmod") or "—",
                entry.get("indexed_at") or "—",
                gsc_synced,
            ), tags=(tag,))

    def _fetch_urls(self):
        site = self._get_site()
        if not site:
            return
        self._fetch_btn.configure(state="disabled")
        self._fetch_status.set("Fetching URLs from sitemap…")

        def worker():
            try:
                sitemap_urls = fetch_urls_from_sitemap_recursive(site["sitemap_url"], set())
                sitemap_urls = filter_urls(sitemap_urls, site)
                existing = migrate_urls(load_json(data_path(site["urls_file"])))

                new_count = 0
                for url in sitemap_urls:
                    if url not in existing:
                        new_count += 1
                        existing[url] = {"indexed": False, "lastmod": sitemap_urls[url]}

                del_count = 0
                for url in list(existing):
                    if url not in sitemap_urls:
                        del_count += 1
                        del existing[url]

                if site.get("track_lastmod"):
                    for url, entry in existing.items():
                        new_lastmod = sitemap_urls.get(url)
                        if new_lastmod and new_lastmod != entry.get("lastmod"):
                            entry["indexed"] = False
                            entry["lastmod"] = new_lastmod

                save_urls_to_file(existing, data_path(site["urls_file"]))
                msg = f"Done: {len(existing)} URLs ({new_count} new, {del_count} removed)"
                self.after(0, lambda: self._finish_fetch(existing, msg))
            except Exception as e:
                self.after(0, lambda: self._finish_fetch(None, f"Error: {e}"))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_fetch(self, urls, msg):
        self._fetch_btn.configure(state="normal")
        self._fetch_status.set(msg)
        if urls is not None:
            self._all_urls = urls
            self._loaded_site = self.site_var.get()
            self._filter_table()

    def _get_site(self):
        config = get_config()
        return next((s for s in config.get("sites", []) if s["name"] == self.site_var.get()), None)

    def _mark_selected_indexed(self):
        selected = self.tree.selection()
        if not selected:
            return
        site = self._get_site()
        if not site:
            return
        for url in selected:
            if url in self._all_urls:
                self._all_urls[url]["indexed"] = True
                self._all_urls[url]["indexed_at"] = str(date.today())
        save_urls_to_file(self._all_urls, data_path(site["urls_file"]))
        self._filter_table()

    def _reset_selected(self):
        selected = self.tree.selection()
        if not selected:
            return
        site = self._get_site()
        if not site:
            return
        for url in selected:
            if url in self._all_urls:
                self._all_urls[url]["indexed"] = False
        save_urls_to_file(self._all_urls, data_path(site["urls_file"]))
        self._filter_table()

    def _reset_all(self):
        site = self._get_site()
        if not site:
            return
        if not messagebox.askyesno("Reset all", "Mark all URLs as not indexed?"):
            return
        for entry in self._all_urls.values():
            entry["indexed"] = False
        save_urls_to_file(self._all_urls, data_path(site["urls_file"]))
        self._filter_table()

    def _check_gsc(self):
        if self._gsc_running:
            return
        site = self._get_site()
        if not site or not site.get("site_url"):
            return
        self._gsc_running = True
        self._gsc_btn.configure(state="disabled", text="Syncing…")
        self._fetch_status.set("Connecting to Google Search Console…")
        threading.Thread(target=self._run_gsc_sync, args=(site,), daemon=True).start()

    def _run_gsc_sync(self, site):
        creds_path = data_path(site["credentials"][0])
        site_url = site["site_url"]
        today = str(date.today())
        try:
            gsc_pages = fetch_indexed_pages(site_url, creds_path)
            marked = 0
            for url, entry in self._all_urls.items():
                if url in gsc_pages:
                    entry["sc_synced_at"] = today
                    if not entry.get("indexed"):
                        entry["indexed"] = True
                        entry["indexed_at"] = today
                        marked += 1
            save_urls_to_file(self._all_urls, data_path(site["urls_file"]))
            msg = f"GSC sync done: {len(gsc_pages)} pages found in GSC, {marked} newly marked as indexed."
            self.after(0, lambda m=msg: self._fetch_status.set(m))
            self.after(0, self._filter_table)
        except Exception as e:
            err = str(e)
            self.after(0, lambda m=err: self._fetch_status.set("GSC error — see details"))
            self.after(0, lambda m=err: messagebox.showerror("GSC Sync Error", m))
        finally:
            self._gsc_running = False
            self.after(0, lambda: self._gsc_btn.configure(state="normal", text="Sync from GSC"))


# ─── Sites Screen ────────────────────────────────────────────────────────────

class SitesScreen(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, corner_radius=0)
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._editing_index = None
        self._dirty = True  # render on first show

        ctk.CTkLabel(self, text="Sites", font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, padx=30, pady=(20, 10), sticky="w"
        )

        self.scroll = ctk.CTkScrollableFrame(self, height=200)
        self.scroll.grid(row=1, column=0, padx=30, pady=5, sticky="nsew")
        self.scroll.grid_columnconfigure(0, weight=1)

        # Form
        form = ctk.CTkFrame(self)
        form.grid(row=2, column=0, padx=30, pady=10, sticky="ew")
        form.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(form, text="Add / Edit Site", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, columnspan=3, padx=10, pady=(10, 6), sticky="w"
        )

        fields = [("Name", "name"), ("Sitemap URL", "sitemap_url"), ("URLs file", "urls_file"),
                  ("GSC Property URL", "site_url")]
        self.form_vars = {}
        for i, (label, key) in enumerate(fields, 1):
            ctk.CTkLabel(form, text=label).grid(row=i, column=0, padx=10, pady=4, sticky="e")
            var = ctk.StringVar()
            self.form_vars[key] = var
            ctk.CTkEntry(form, textvariable=var).grid(row=i, column=1, padx=10, pady=4, sticky="ew")

        ctk.CTkLabel(form, text="Use sc-domain:example.com (recommended)",
                     text_color="gray", font=ctk.CTkFont(size=10)).grid(
            row=4, column=2, padx=(0, 10), sticky="w"
        )

        ctk.CTkLabel(form, text="Credentials").grid(row=5, column=0, padx=10, pady=4, sticky="ne")
        creds_container = ctk.CTkFrame(form, fg_color="transparent")
        creds_container.grid(row=5, column=1, columnspan=2, padx=10, pady=4, sticky="ew")
        creds_container.grid_columnconfigure(0, weight=1)
        self._creds_list_frame = ctk.CTkScrollableFrame(creds_container, height=80)
        self._creds_list_frame.grid(row=0, column=0, sticky="ew")
        self._creds_list_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(creds_container, text="+ Add credentials", width=140,
                      command=self._add_credentials).grid(row=1, column=0, pady=(4, 0), sticky="w")
        self._creds_list = []

        btn_frame = ctk.CTkFrame(form)
        btn_frame.grid(row=6, column=0, columnspan=3, pady=10)
        ctk.CTkButton(btn_frame, text="Save", command=self._save_site).pack(side="left", padx=6)
        ctk.CTkButton(btn_frame, text="Clear", command=self._clear_form).pack(side="left", padx=6)

    def on_show(self):
        if self._dirty:
            self._render_sites()
            self._dirty = False

    def _render_sites(self):
        for w in self.scroll.winfo_children():
            w.destroy()
        config = get_config()
        for i, site in enumerate(config.get("sites", [])):
            row = ctk.CTkFrame(self.scroll)
            row.grid(row=i, column=0, sticky="ew", pady=3)
            row.grid_columnconfigure(0, weight=1)
            capacity = len(site["credentials"]) * 200
            ctk.CTkLabel(row,
                         text=f"{site['name']}  —  {site['sitemap_url']}  —  {capacity} urls/día",
                         anchor="w").grid(row=0, column=0, padx=10, sticky="w")
            ctk.CTkButton(row, text="Edit", width=60,
                          command=lambda idx=i: self._edit_site(idx)).grid(row=0, column=1, padx=4)
            ctk.CTkButton(row, text="Delete", width=60, fg_color="red", hover_color="#a00000",
                          command=lambda idx=i: self._delete_site(idx)).grid(row=0, column=2, padx=4)

    def _render_creds_list(self):
        for w in self._creds_list_frame.winfo_children():
            w.destroy()
        for idx, creds_file in enumerate(self._creds_list):
            row = ctk.CTkFrame(self._creds_list_frame, fg_color="transparent")
            row.grid(row=idx, column=0, sticky="ew", pady=1)
            row.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(row, text=creds_file, anchor="w").grid(
                row=0, column=0, padx=(4, 8), sticky="w")
            ctk.CTkButton(row, text="Remove", width=70,
                          fg_color="gray30", hover_color="gray20",
                          command=lambda i=idx: self._remove_credentials(i)).grid(
                row=0, column=1, padx=(0, 4))

    def _add_credentials(self):
        path = filedialog.askopenfilename(
            title="Select credentials JSON",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir=DATA_DIR,
        )
        if path:
            rel = os.path.relpath(path, DATA_DIR)
            if rel not in self._creds_list:
                self._creds_list.append(rel)
                self._render_creds_list()

    def _remove_credentials(self, idx):
        if 0 <= idx < len(self._creds_list):
            del self._creds_list[idx]
            self._render_creds_list()

    def _clear_form(self):
        self._editing_index = None
        for var in self.form_vars.values():
            var.set("")
        self._creds_list = []
        self._render_creds_list()

    def _edit_site(self, idx):
        config = get_config()
        site = config["sites"][idx]
        self._editing_index = idx
        self.form_vars["name"].set(site.get("name", ""))
        self.form_vars["sitemap_url"].set(site.get("sitemap_url", ""))
        self.form_vars["urls_file"].set(site.get("urls_file", ""))
        self.form_vars["site_url"].set(site.get("site_url", ""))
        self._creds_list = list(site.get("credentials", ["credentials.json"]))
        self._render_creds_list()

    def _delete_site(self, idx):
        config = get_config()
        name = config["sites"][idx]["name"]
        if not messagebox.askyesno("Delete site", f"Delete site '{name}'?"):
            return
        del config["sites"][idx]
        save_config(config)
        self._dirty = True
        self._render_sites()

    def _save_site(self):
        name = self.form_vars["name"].get().strip()
        sitemap_url = self.form_vars["sitemap_url"].get().strip()
        if not name or not sitemap_url:
            messagebox.showwarning("Missing fields", "Name and Sitemap URL are required.")
            return

        config = get_config()
        site_data = {
            "name": name,
            "sitemap_url": sitemap_url,
            "credentials": self._creds_list if self._creds_list else ["credentials.json"],
            "urls_file": self.form_vars["urls_file"].get().strip() or f"urls_{name}.json",
            "site_url": self.form_vars["site_url"].get().strip(),
            "track_lastmod": False,
            "skip_extensions": DEFAULT_SKIP_EXTENSIONS,
            "exclude_patterns": [],
            "include_patterns": [],
        }

        if self._editing_index is not None:
            existing = config["sites"][self._editing_index]
            for key in ("track_lastmod", "skip_extensions", "exclude_patterns", "include_patterns"):
                site_data[key] = existing.get(key, site_data[key])
            config["sites"][self._editing_index] = site_data
        else:
            config.setdefault("sites", []).append(site_data)

        save_config(config)
        self._clear_form()
        self._dirty = True
        self._render_sites()


# ─── Settings Screen ─────────────────────────────────────────────────────────

class SettingsScreen(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, corner_radius=0)
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(self, text="Settings", font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, padx=30, pady=(20, 10), sticky="w"
        )

        sel = ctk.CTkFrame(self)
        sel.grid(row=1, column=0, padx=30, pady=5, sticky="w")
        ctk.CTkLabel(sel, text="Site:").pack(side="left", padx=(0, 8))
        self.site_var = ctk.StringVar()
        self.site_dropdown = ctk.CTkOptionMenu(sel, variable=self.site_var, width=220,
                                               command=lambda _: self._load_settings())
        self.site_dropdown.pack(side="left")

        form = ctk.CTkScrollableFrame(self)
        form.grid(row=2, column=0, padx=30, pady=10, sticky="nsew")
        form.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(form, text="Track lastmod").grid(row=0, column=0, padx=10, pady=8, sticky="w")
        self.track_lastmod_var = ctk.BooleanVar()
        ctk.CTkSwitch(form, text="", variable=self.track_lastmod_var).grid(row=0, column=1, sticky="w")

        self.list_vars = {}
        for i, (label, key) in enumerate([
            ("Skip extensions", "skip_extensions"),
            ("Exclude patterns", "exclude_patterns"),
            ("Include patterns", "include_patterns"),
        ], 1):
            ctk.CTkLabel(form, text=label, font=ctk.CTkFont(weight="bold")).grid(
                row=i * 2 - 1, column=0, columnspan=2, padx=10, pady=(12, 2), sticky="w"
            )
            ctk.CTkLabel(form, text="(one per line)", text_color="gray").grid(
                row=i * 2 - 1, column=1, padx=10, sticky="e"
            )
            tb = ctk.CTkTextbox(form, height=80)
            tb.grid(row=i * 2, column=0, columnspan=2, padx=10, pady=(0, 4), sticky="ew")
            self.list_vars[key] = tb

        ctk.CTkButton(self, text="Save settings", command=self._save_settings).grid(
            row=3, column=0, padx=30, pady=10, sticky="w"
        )

    def on_show(self):
        config = get_config()
        names = [s["name"] for s in config.get("sites", [])]
        self.site_dropdown.configure(values=names)
        if names and self.site_var.get() not in names:
            self.site_var.set(names[0])
        self._load_settings(config)

    def _load_settings(self, config=None):
        if config is None:
            config = get_config()
        site = next((s for s in config.get("sites", []) if s["name"] == self.site_var.get()), None)
        if not site:
            return
        self.track_lastmod_var.set(site.get("track_lastmod", False))
        for key, tb in self.list_vars.items():
            tb.delete("1.0", "end")
            tb.insert("1.0", "\n".join(site.get(key, [])))

    def _save_settings(self):
        config = get_config()
        site = next((s for s in config.get("sites", []) if s["name"] == self.site_var.get()), None)
        if not site:
            messagebox.showwarning("No site", "Select a site first.")
            return
        site["track_lastmod"] = self.track_lastmod_var.get()
        for key, tb in self.list_vars.items():
            raw = tb.get("1.0", "end").strip()
            site[key] = [line.strip() for line in raw.splitlines() if line.strip()]
        save_config(config)
        messagebox.showinfo("Saved", "Settings saved.")


# ─── Help content ────────────────────────────────────────────────────────────

HELP_CONTENT = {
    "English": [
        (
            "① How to Add a Site",
            """\
1. Click "Sites" in the sidebar.

2. Fill in the form:
   • Name — A short identifier for your site (e.g. "mysite"). No spaces.
   • Sitemap URL — The full URL to your sitemap, e.g.:
       https://example.com/sitemap.xml
       https://example.com/sitemap-index.xml
   • Credentials — Path to your Google service account JSON file.
     Click "Browse" to locate it (see section ② for how to get it).
   • URLs file — Leave blank. It will be created automatically as
     urls_{name}.json next to the app.

3. Click "Save". The site will appear in the list above the form.""",
        ),
        (
            "② Google Credentials — Step by Step",
            """\
You need a Google service account to use the Indexing API.

STEP 1 — Create a Google Cloud Project
  • Go to https://console.cloud.google.com
  • Click the project selector at the top → "New Project"
  • Give it a name and click "Create"

STEP 2 — Enable the Web Search Indexing API
  • In the search bar type "Web Search Indexing API"
  • Check that the project you just created appears in the square at the top left.
    If not, click on it and select it.
  • Click on it → click "ENABLE"

STEP 3 — Create a Service Account
  • Click the menu → Go to IAM & Admin → Service Accounts → "+ Create Service Account"
  • Enter any name → click "Create and Continue" → "Done"
  • Click the service account you just created
  • Go to the "Keys" tab → "Add Key" → "Create new key" → JSON → "Create"
  • A .json file will be downloaded. Rename it to credentials_[yourproject].json and
    place it in the same folder as the app (SmartInstantIndex.exe)

STEP 4 — Add the service account to Google Search Console
  • Copy the service account email (looks like: name@project.iam.gserviceaccount.com)
  • Go to https://search.google.com/search-console
  • Select your property → Settings → Users and permissions
  • Click "Add user" → paste the email → set role to "Owner" → Add

STEP 5 — Done!
  • In SmartInstantIndex, go to Sites → Browse → select your credentials.json

─────────────────────────────────────────
OPTIONAL — Enable "Sync from GSC" feature
─────────────────────────────────────────
This feature checks which URLs are actually indexed in Google Search Console
and marks them automatically. It requires one extra step:

1. In Google Cloud Console, enable the "Google Search Console API"
   (same steps as STEP 2 above, but search for "Google Search Console API"):
   • In the search bar type "Google Search Console API"
   • Check that your project appears in the square at the top left.
     If not, click on it and select it.
   • Click on it → click "ENABLE"

2. In SmartInstantIndex → Sites, fill in the "GSC Property URL" field.
   The value must match exactly how your site appears in Search Console:

   • Domain property  →  sc-domain:example.com
     (use this if you verified via DNS — most common)

   • URL prefix property  →  https://example.com/
     (use this if you verified by uploading an HTML file or meta tag)

   To check your property type: open Search Console, look at the
   property list on the left — domain properties show a globe icon,
   URL prefix properties show a link icon.""",
        ),
        (
            "③ Dashboard",
            """\
The Dashboard is your main control panel.

• Site selector — Choose which site you want to work with.

• Stats cards:
    Total URLs   — Number of URLs found in your sitemap.
    Indexed      — URLs already submitted to Google.
    Pending      — URLs not yet submitted.
    Quota left   — How many URLs you can still submit today
                   (Google allows max 200 per day per GCP project).

• Run Indexing button — Starts the indexing process:
    1. Fetches your sitemap and syncs any new/removed URLs.
    2. Resets URLs whose lastmod changed (if Track lastmod is ON).
    3. Submits pending URLs to Google up to the daily quota.
    The progress bar and log show real-time status.

• If you see an error about credentials, check that credentials.json
  is in the same folder as the app and the path in Sites is correct.""",
        ),
        (
            "④ URLs Panel",
            """\
The URLs panel shows every URL found in your sitemap and its status.

• Green ✓ — URL has been submitted to Google.
• Gray  ✗ — URL is pending (will be submitted on next run).

• GSC Sync column — ✓ means Google confirmed this URL is indexed
  (visible in Search Console data). — means not yet synced or not found.
  Use the "Sync from GSC" button to update this column.

• Search box — Type any text to filter the list instantly.

• Reset selected — Select one or more rows (use Ctrl+click or
  Shift+click for multiple) then click this button to mark them as
  pending. They will be resubmitted on the next run.

• Reset all — Marks ALL URLs as pending. Use this if you want to
  force Google to re-index everything from scratch.

• Sync from GSC — Fetches all indexed pages from Google Search Console
  and marks matching URLs as indexed. Requires "GSC Property URL" to be
  set in Sites. See the Setup tab for configuration details.""",
        ),
        (
            "⑤ Settings",
            """\
Settings are per-site. Select the site first using the dropdown.

• Track lastmod (ON/OFF)
    When ON, if your sitemap reports a new lastmod date for a URL,
    that URL is automatically reset to pending on the next run.
    Useful for blogs or sites that update their content frequently.

• Skip extensions
    File types to ignore completely (one per line). Default list
    includes images, PDFs, videos and archives:
      .jpg  .jpeg  .png  .gif  .webp  .svg  .pdf  .mp4  .zip

• Exclude patterns
    If a URL contains any of these strings, it is ignored.
    Example: adding "/tag/" will skip all tag pages.

• Include patterns (whitelist)
    If this list is NOT empty, ONLY URLs that contain at least one
    of these strings will be processed. All others are ignored.
    Example: adding "/blog/" will process only blog posts.
    Note: Exclude always wins over Include.

Click "Save settings" to apply changes.""",
        ),
        (
            "⑥ Multiplying Daily Quota",
            """\
Google's 200 URLs/day limit is per GCP project, not per service account.
By assigning multiple credentials (from different GCP projects) to a site,
SmartInstantIndex automatically rotates to the next credential when the
current one hits its daily limit.

Example: 3 credentials → 600 URLs/day for the same site.

HOW TO SET IT UP

For each additional GCP project you want to add:

STEP 1 — Create a new GCP project
  • Go to https://console.cloud.google.com
  • Click the project selector → "New Project"
  • Give it a name and click "Create"

STEP 2 — Enable the Web Search Indexing API
  • In the search bar type "Web Search Indexing API"
  • Make sure the new project is selected in the top-left square
  • Click it → "ENABLE"

STEP 3 — Create a Service Account and download its key
  • Menu → IAM & Admin → Service Accounts → "+ Create Service Account"
  • Enter any name → "Create and Continue" → "Done"
  • Click the account → "Keys" tab → "Add Key" → JSON → "Create"
  • Save the downloaded .json file next to the app

STEP 4 — Add the service account to Google Search Console
  • Copy the service account email
  • Go to Search Console → your property → Settings → Users and permissions
  • "Add user" → paste the email → role "Owner" → Add
  • You can add multiple service accounts to the same property

STEP 5 — Assign the credentials in SmartInstantIndex
  • Go to Sites → Edit your site
  • Click "+ Add credentials" and select the new .json file
  • Repeat for each additional credentials file
  • Click "Save"

The Dashboard shows a progress bar per credential so you can see
how much quota each one has used today.""",
        ),
    ],
    "Español": [
        (
            "① Cómo añadir un site",
            """\
1. Haz clic en "Sites" en la barra lateral.

2. Rellena el formulario:
   • Name — Un identificador corto para tu web (ej. "miweb"). Sin espacios.
   • Sitemap URL — La URL completa de tu sitemap, por ejemplo:
       https://ejemplo.com/sitemap.xml
       https://ejemplo.com/sitemap-index.xml
   • Credentials — Ruta al archivo JSON de tu cuenta de servicio de Google.
     Haz clic en "Browse" para buscarlo (ver sección ② para obtenerlo).
   • URLs file — Déjalo en blanco. Se creará automáticamente como
     urls_{name}.json junto a la app.

3. Haz clic en "Save". El site aparecerá en la lista superior.""",
        ),
        (
            "② Credenciales de Google — Paso a paso",
            """\
Necesitas una cuenta de servicio de Google para usar la Indexing API.

PASO 1 — Crear un proyecto en Google Cloud
  • Ve a https://console.cloud.google.com
  • Haz clic en el selector de proyectos → "Nuevo proyecto"
  • Ponle un nombre y haz clic en "Crear"

PASO 2 — Activar la Web Search Indexing API
  • En el buscador escribe "Web Search Indexing API"
  • Comprueba que en el cuadrado de arriba a la izquierda aparece el proyecto
    que acabas de crear. Si no es así, haz clic en él y selecciónalo.
  • Haz clic en ella → haz clic en "HABILITAR"

PASO 3 — Crear una cuenta de servicio
  • Pulsa en el menú → Ve a IAM y administración → Cuentas de servicio → "+ Crear cuenta de servicio"
  • Escribe cualquier nombre → "Crear y continuar" → "Listo"
  • Haz clic en la cuenta recién creada
  • Pestaña "Claves" → "Agregar clave" → "Crear clave nueva" → JSON → "Crear"
  • Se descargará un archivo .json. Renómbralo como credentials_[tuproyecto].json y
    colócalo en la misma carpeta que la app (SmartInstantIndex.exe)

PASO 4 — Añadir la cuenta de servicio a Google Search Console
  • Copia el email de la cuenta de servicio (ej: nombre@proyecto.iam.gserviceaccount.com)
  • Ve a https://search.google.com/search-console
  • Selecciona tu propiedad → Ajustes → Usuarios y permisos
  • Haz clic en "Añadir usuario" → pega el email → rol "Propietario" → Añadir

PASO 5 — ¡Listo!
  • En SmartInstantIndex, ve a Sites → Browse → selecciona tu credentials.json

─────────────────────────────────────────
OPCIONAL — Activar "Sync from GSC"
─────────────────────────────────────────
Esta función consulta qué URLs están indexadas en Google Search Console
y las marca automáticamente. Requiere un paso adicional:

1. En Google Cloud Console, activa la API "Google Search Console API"
   (igual que el PASO 2 de arriba, pero buscando "Google Search Console API"):
   • En el buscador escribe "Google Search Console API"
   • Comprueba que tu proyecto aparece en el cuadrado de arriba a la izquierda.
     Si no, haz clic en él y selecciónalo.
   • Haz clic en ella → haz clic en "HABILITAR"

2. En SmartInstantIndex → Sites, rellena el campo "GSC Property URL".
   El valor debe coincidir exactamente con cómo aparece tu sitio en Search Console:

   • Propiedad de dominio  →  sc-domain:ejemplo.com
     (úsala si verificaste por DNS — lo más habitual)

   • Propiedad de prefijo de URL  →  https://ejemplo.com/
     (úsala si verificaste con un archivo HTML o meta tag)

   Para saber qué tipo tienes: abre Search Console y mira la lista de
   propiedades a la izquierda — las de dominio tienen un icono de globo,
   las de prefijo de URL tienen un icono de enlace.""",
        ),
        (
            "③ Dashboard",
            """\
El Dashboard es tu panel de control principal.

• Selector de site — Elige con qué site quieres trabajar.

• Tarjetas de estadísticas:
    Total URLs   — Número de URLs en tu sitemap.
    Indexed      — URLs ya enviadas a Google.
    Pending      — URLs pendientes de enviar.
    Quota left   — Cuántas URLs puedes enviar hoy
                   (Google permite máx. 200 al día por proyecto GCP).

• Botón Run Indexing — Inicia el proceso de indexación:
    1. Descarga tu sitemap y sincroniza URLs nuevas/eliminadas.
    2. Resetea URLs cuyo lastmod cambió (si Track lastmod está activado).
    3. Envía las URLs pendientes a Google hasta agotar la cuota diaria.
    La barra de progreso y el log muestran el estado en tiempo real.

• Si ves un error de credenciales, comprueba que credentials.json esté
  en la misma carpeta que la app y que la ruta en Sites sea correcta.""",
        ),
        (
            "④ Panel de URLs",
            """\
El panel de URLs muestra todas las URLs de tu sitemap y su estado.

• Verde ✓ — URL enviada a Google.
• Gris  ✗ — URL pendiente (se enviará en el próximo run).

• Columna GSC Sync — ✓ significa que Google confirma que esta URL está
  indexada (aparece en los datos de Search Console). — significa que aún
  no se ha sincronizado o no se encontró.
  Usa el botón "Sync from GSC" para actualizar esta columna.

• Buscador — Escribe cualquier texto para filtrar la lista al instante.

• Reset selected — Selecciona una o varias filas (usa Ctrl+clic o
  Shift+clic para seleccionar varias) y haz clic en este botón para
  marcarlas como pendientes. Se reenviarán en el próximo run.

• Reset all — Marca TODAS las URLs como pendientes. Úsalo si quieres
  forzar a Google a re-indexar todo desde cero.

• Sync from GSC — Obtiene todas las páginas indexadas de Google Search
  Console y marca las URLs coincidentes como indexadas. Requiere que
  "GSC Property URL" esté configurado en Sites. Ver pestaña Configuración.""",
        ),
        (
            "⑤ Settings",
            """\
La configuración es por site. Selecciona primero el site con el desplegable.

• Track lastmod (ON/OFF)
    Cuando está ON, si tu sitemap reporta una nueva fecha lastmod para
    una URL, esa URL se resetea automáticamente a pendiente en el
    siguiente run. Útil para blogs o webs que actualizan contenido.

• Skip extensions
    Tipos de archivo a ignorar completamente (uno por línea). La lista
    por defecto incluye imágenes, PDFs, vídeos y archivos comprimidos:
      .jpg  .jpeg  .png  .gif  .webp  .svg  .pdf  .mp4  .zip

• Exclude patterns
    Si una URL contiene cualquiera de estas cadenas, se ignora.
    Ejemplo: añadir "/etiqueta/" omitirá todas las páginas de etiquetas.

• Include patterns (lista blanca)
    Si esta lista NO está vacía, solo se procesarán las URLs que
    contengan al menos una de estas cadenas. Las demás se ignoran.
    Ejemplo: añadir "/blog/" procesa solo las entradas del blog.
    Nota: Exclude siempre tiene prioridad sobre Include.

Haz clic en "Save settings" para aplicar los cambios.""",
        ),
        (
            "⑥ Multiplicar la cuota diaria",
            """\
El límite de 200 URLs/día es por proyecto de GCP, no por cuenta de servicio.
Asignando varias credenciales (de proyectos GCP distintos) a un mismo site,
SmartInstantIndex pasa automáticamente a la siguiente cuando la actual agota
su cuota diaria.

Ejemplo: 3 credenciales → 600 URLs/día para el mismo site.

CÓMO CONFIGURARLO

Repite estos pasos por cada proyecto GCP adicional que quieras añadir:

PASO 1 — Crea un nuevo proyecto en GCP
  • Ve a https://console.cloud.google.com
  • Haz clic en el selector de proyectos → "Nuevo proyecto"
  • Ponle un nombre y haz clic en "Crear"

PASO 2 — Activa la Web Search Indexing API
  • En el buscador escribe "Web Search Indexing API"
  • Comprueba que el nuevo proyecto aparece en el cuadrado de arriba a la izquierda
  • Haz clic en ella → "HABILITAR"

PASO 3 — Crea una cuenta de servicio y descarga su clave
  • Menú → IAM y administración → Cuentas de servicio → "+ Crear cuenta de servicio"
  • Escribe cualquier nombre → "Crear y continuar" → "Listo"
  • Haz clic en la cuenta → pestaña "Claves" → "Agregar clave" → JSON → "Crear"
  • Guarda el archivo .json descargado junto a la app

PASO 4 — Añade la cuenta de servicio a Google Search Console
  • Copia el email de la cuenta de servicio
  • Ve a Search Console → tu propiedad → Ajustes → Usuarios y permisos
  • "Añadir usuario" → pega el email → rol "Propietario" → Añadir
  • Puedes añadir varias cuentas de servicio a la misma propiedad

PASO 5 — Asigna las credenciales en SmartInstantIndex
  • Ve a Sites → edita tu site
  • Haz clic en "+ Add credentials" y selecciona el nuevo archivo .json
  • Repite por cada archivo de credenciales adicional
  • Haz clic en "Save"

El Dashboard muestra una barra de progreso por credencial para que veas
cuánta cuota ha consumido cada una hoy.""",
        ),
    ],
    "Français": [
        (
            "① Comment ajouter un site",
            """\
1. Cliquez sur "Sites" dans la barre latérale.

2. Remplissez le formulaire :
   • Name — Un identifiant court pour votre site (ex. "monsite"). Sans espaces.
   • Sitemap URL — L'URL complète de votre sitemap, par exemple :
       https://exemple.com/sitemap.xml
       https://exemple.com/sitemap-index.xml
   • Credentials — Chemin vers votre fichier JSON de compte de service Google.
     Cliquez sur "Browse" pour le localiser (voir section ② pour l'obtenir).
   • URLs file — Laissez vide. Il sera créé automatiquement sous le nom
     urls_{name}.json dans le même dossier que l'application.

3. Cliquez sur "Save". Le site apparaîtra dans la liste.""",
        ),
        (
            "② Identifiants Google — Étape par étape",
            """\
Vous avez besoin d'un compte de service Google pour utiliser l'Indexing API.

ÉTAPE 1 — Créer un projet Google Cloud
  • Rendez-vous sur https://console.cloud.google.com
  • Cliquez sur le sélecteur de projet → "Nouveau projet"
  • Donnez-lui un nom et cliquez sur "Créer"

ÉTAPE 2 — Activer l'API Web Search Indexing
  • Dans la barre de recherche, tapez "Web Search Indexing API"
  • Vérifiez que le projet que vous venez de créer apparaît dans le carré en haut à gauche.
    Si ce n'est pas le cas, cliquez dessus et sélectionnez-le.
  • Cliquez dessus → cliquez sur "ACTIVER"

ÉTAPE 3 — Créer un compte de service
  • Cliquez sur le menu → Allez dans IAM et administration → Comptes de service → "+ Créer"
  • Entrez un nom → "Créer et continuer" → "OK"
  • Cliquez sur le compte créé → onglet "Clés"
  • "Ajouter une clé" → "Créer une clé" → JSON → "Créer"
  • Un fichier .json sera téléchargé. Renommez-le credentials_[votreprojet].json et
    placez-le dans le même dossier que l'application (SmartInstantIndex.exe)

ÉTAPE 4 — Ajouter le compte de service à Google Search Console
  • Copiez l'email du compte (ex : nom@projet.iam.gserviceaccount.com)
  • Allez sur https://search.google.com/search-console
  • Sélectionnez votre propriété → Paramètres → Utilisateurs et autorisations
  • "Ajouter un utilisateur" → collez l'email → rôle "Propriétaire" → Ajouter

ÉTAPE 5 — Terminé !
  • Dans SmartInstantIndex, allez dans Sites → Browse → sélectionnez credentials.json

─────────────────────────────────────────
OPTIONNEL — Activer "Sync from GSC"
─────────────────────────────────────────
Cette fonction vérifie quelles URLs sont réellement indexées dans Google Search Console
et les marque automatiquement. Elle nécessite une étape supplémentaire :

1. Dans Google Cloud Console, activez l'API "Google Search Console API"
   (mêmes étapes que l'ÉTAPE 2 ci-dessus, mais en recherchant "Google Search Console API") :
   • Dans la barre de recherche, tapez "Google Search Console API"
   • Vérifiez que votre projet apparaît dans le carré en haut à gauche.
     Si ce n'est pas le cas, cliquez dessus et sélectionnez-le.
   • Cliquez dessus → cliquez sur "ACTIVER"

2. Dans SmartInstantIndex → Sites, remplissez le champ "GSC Property URL".
   La valeur doit correspondre exactement à l'affichage de votre site dans Search Console :

   • Propriété de domaine  →  sc-domain:exemple.com
     (si vous avez vérifié via DNS — le plus courant)

   • Propriété par préfixe d'URL  →  https://exemple.com/
     (si vous avez vérifié avec un fichier HTML ou une balise meta)

   Pour vérifier votre type : ouvrez Search Console et regardez la liste des
   propriétés à gauche — les propriétés de domaine ont une icône de globe,
   les propriétés par préfixe d'URL ont une icône de lien.""",
        ),
        (
            "③ Dashboard",
            """\
Le Dashboard est votre panneau de contrôle principal.

• Sélecteur de site — Choisissez le site avec lequel travailler.

• Cartes de statistiques :
    Total URLs   — Nombre d'URLs dans votre sitemap.
    Indexed      — URLs déjà soumises à Google.
    Pending      — URLs en attente de soumission.
    Quota left   — Combien d'URLs vous pouvez encore soumettre aujourd'hui
                   (Google autorise max. 200 par jour par projet GCP).

• Bouton Run Indexing — Lance le processus d'indexation :
    1. Récupère votre sitemap et synchronise les URLs nouvelles/supprimées.
    2. Réinitialise les URLs dont le lastmod a changé (si Track lastmod est ON).
    3. Soumet les URLs en attente à Google jusqu'au quota journalier.
    La barre de progression et le journal affichent l'état en temps réel.

• En cas d'erreur de credentials, vérifiez que credentials.json est bien
  dans le même dossier que l'app et que le chemin dans Sites est correct.""",
        ),
        (
            "④ Panneau URLs",
            """\
Le panneau URLs affiche toutes les URLs de votre sitemap et leur état.

• Vert  ✓ — URL soumise à Google.
• Gris  ✗ — URL en attente (sera soumise lors du prochain run).

• Barre de recherche — Tapez du texte pour filtrer la liste instantanément.

• Reset selected — Sélectionnez une ou plusieurs lignes (Ctrl+clic ou
  Shift+clic pour plusieurs) puis cliquez pour les marquer comme en attente.
  Elles seront resoumises lors du prochain run.

• Reset all — Marque TOUTES les URLs comme en attente. À utiliser si vous
  souhaitez forcer Google à réindexer tout depuis le début.""",
        ),
        (
            "⑤ Settings",
            """\
Les paramètres sont par site. Sélectionnez d'abord le site dans la liste.

• Track lastmod (ON/OFF)
    Quand ON, si votre sitemap signale une nouvelle date lastmod pour une
    URL, cette URL est automatiquement remise en attente lors du prochain run.
    Utile pour les blogs ou les sites qui mettent à jour leur contenu.

• Skip extensions
    Types de fichiers à ignorer complètement (un par ligne). La liste
    par défaut inclut images, PDFs, vidéos et archives :
      .jpg  .jpeg  .png  .gif  .webp  .svg  .pdf  .mp4  .zip

• Exclude patterns
    Si une URL contient l'une de ces chaînes, elle est ignorée.
    Exemple : ajouter "/tag/" ignorera toutes les pages de tags.

• Include patterns (liste blanche)
    Si cette liste n'est PAS vide, seules les URLs contenant au moins
    une de ces chaînes seront traitées. Toutes les autres sont ignorées.
    Exemple : ajouter "/blog/" traite uniquement les articles de blog.
    Note : Exclude a toujours priorité sur Include.

Cliquez sur "Save settings" pour appliquer les modifications.""",
        ),
        (
            "⑥ Multiplier le quota journalier",
            """\
La limite de 200 URLs/jour est par projet GCP, pas par compte de service.
En assignant plusieurs identifiants (issus de projets GCP différents) à un
site, SmartInstantIndex passe automatiquement au suivant lorsque le quota
du premier est épuisé.

Exemple : 3 identifiants → 600 URLs/jour pour le même site.

COMMENT CONFIGURER

Répétez ces étapes pour chaque projet GCP supplémentaire :

ÉTAPE 1 — Créer un nouveau projet GCP
  • Rendez-vous sur https://console.cloud.google.com
  • Cliquez sur le sélecteur de projet → "Nouveau projet"
  • Donnez-lui un nom et cliquez sur "Créer"

ÉTAPE 2 — Activer l'API Web Search Indexing
  • Dans la barre de recherche, tapez "Web Search Indexing API"
  • Vérifiez que le nouveau projet est sélectionné en haut à gauche
  • Cliquez dessus → "ACTIVER"

ÉTAPE 3 — Créer un compte de service et télécharger sa clé
  • Menu → IAM et administration → Comptes de service → "+ Créer"
  • Entrez un nom → "Créer et continuer" → "OK"
  • Cliquez sur le compte → onglet "Clés" → "Ajouter une clé" → JSON → "Créer"
  • Enregistrez le fichier .json téléchargé dans le dossier de l'application

ÉTAPE 4 — Ajouter le compte de service à Google Search Console
  • Copiez l'email du compte de service
  • Allez dans Search Console → votre propriété → Paramètres → Utilisateurs
  • "Ajouter un utilisateur" → collez l'email → rôle "Propriétaire" → Ajouter
  • Vous pouvez ajouter plusieurs comptes de service à la même propriété

ÉTAPE 5 — Assigner les identifiants dans SmartInstantIndex
  • Allez dans Sites → modifiez votre site
  • Cliquez sur "+ Add credentials" et sélectionnez le nouveau fichier .json
  • Répétez pour chaque fichier d'identifiants supplémentaire
  • Cliquez sur "Save"

Le Dashboard affiche une barre de progression par identifiant pour voir
le quota utilisé par chacun aujourd'hui.""",
        ),
    ],
    "Português": [
        (
            "① Como adicionar um site",
            """\
1. Clique em "Sites" na barra lateral.

2. Preencha o formulário:
   • Name — Um identificador curto para o seu site (ex. "meusite"). Sem espaços.
   • Sitemap URL — A URL completa do seu sitemap, por exemplo:
       https://exemplo.com/sitemap.xml
       https://exemplo.com/sitemap-index.xml
   • Credentials — Caminho para o ficheiro JSON da sua conta de serviço Google.
     Clique em "Browse" para o localizar (ver secção ② para obtê-lo).
   • URLs file — Deixe em branco. Será criado automaticamente como
     urls_{name}.json na mesma pasta da aplicação.

3. Clique em "Save". O site aparecerá na lista.""",
        ),
        (
            "② Credenciais do Google — Passo a passo",
            """\
Precisa de uma conta de serviço Google para usar a Indexing API.

PASSO 1 — Criar um projeto no Google Cloud
  • Aceda a https://console.cloud.google.com
  • Clique no seletor de projeto → "Novo projeto"
  • Dê-lhe um nome e clique em "Criar"

PASSO 2 — Ativar a Web Search Indexing API
  • Na barra de pesquisa escreva "Web Search Indexing API"
  • Verifique que o projeto que acabou de criar aparece no quadrado no canto superior esquerdo.
    Se não aparecer, clique nele e selecione-o.
  • Clique nela → clique em "ATIVAR"

PASSO 3 — Criar uma conta de serviço
  • Clique no menu → Vá a IAM e administração → Contas de serviço → "+ Criar conta de serviço"
  • Introduza um nome → "Criar e continuar" → "Concluído"
  • Clique na conta criada → separador "Chaves"
  • "Adicionar chave" → "Criar nova chave" → JSON → "Criar"
  • Um ficheiro .json será descarregado. Renomeie-o para credentials_[seuprojeto].json e
    coloque-o na mesma pasta da aplicação (SmartInstantIndex.exe)

PASSO 4 — Adicionar a conta de serviço ao Google Search Console
  • Copie o email da conta (ex: nome@projeto.iam.gserviceaccount.com)
  • Aceda a https://search.google.com/search-console
  • Selecione a sua propriedade → Definições → Utilizadores e permissões
  • "Adicionar utilizador" → cole o email → função "Proprietário" → Adicionar

PASSO 5 — Concluído!
  • No SmartInstantIndex, vá a Sites → Browse → selecione credentials.json

─────────────────────────────────────────
OPCIONAL — Ativar "Sync from GSC"
─────────────────────────────────────────
Esta função verifica quais URLs estão realmente indexadas no Google Search Console
e marca-as automaticamente. Requer um passo adicional:

1. No Google Cloud Console, ative a API "Google Search Console API"
   (os mesmos passos do PASSO 2 acima, mas pesquisando "Google Search Console API"):
   • Na barra de pesquisa escreva "Google Search Console API"
   • Verifique que o seu projeto aparece no quadrado no canto superior esquerdo.
     Se não aparecer, clique nele e selecione-o.
   • Clique nela → clique em "ATIVAR"

2. No SmartInstantIndex → Sites, preencha o campo "GSC Property URL".
   O valor deve corresponder exatamente a como o seu site aparece no Search Console:

   • Propriedade de domínio  →  sc-domain:exemplo.com
     (use se verificou via DNS — o mais comum)

   • Propriedade de prefixo de URL  →  https://exemplo.com/
     (use se verificou com um ficheiro HTML ou meta tag)

   Para verificar o seu tipo: abra o Search Console e veja a lista de
   propriedades à esquerda — as de domínio têm um ícone de globo,
   as de prefixo de URL têm um ícone de ligação.""",
        ),
        (
            "③ Dashboard",
            """\
O Dashboard é o seu painel de controlo principal.

• Seletor de site — Escolha com qual site pretende trabalhar.

• Cartões de estatísticas:
    Total URLs   — Número de URLs no seu sitemap.
    Indexed      — URLs já submetidas ao Google.
    Pending      — URLs ainda por submeter.
    Quota left   — Quantas URLs pode ainda submeter hoje
                   (Google permite máx. 200 por dia por projeto GCP).

• Botão Run Indexing — Inicia o processo de indexação:
    1. Obtém o sitemap e sincroniza URLs novas/removidas.
    2. Repõe URLs cujo lastmod mudou (se Track lastmod estiver ON).
    3. Submete as URLs pendentes ao Google até ao limite diário.
    A barra de progresso e o registo mostram o estado em tempo real.

• Se receber um erro de credenciais, verifique que credentials.json está
  na mesma pasta da aplicação e que o caminho em Sites está correto.""",
        ),
        (
            "④ Painel de URLs",
            """\
O painel de URLs mostra todas as URLs do seu sitemap e o respetivo estado.

• Verde ✓ — URL submetida ao Google.
• Cinza ✗ — URL pendente (será submetida no próximo run).

• Caixa de pesquisa — Escreva qualquer texto para filtrar a lista instantaneamente.

• Reset selected — Selecione uma ou mais linhas (Ctrl+clique ou
  Shift+clique para várias) e clique para as marcar como pendentes.
  Serão resubmetidas no próximo run.

• Reset all — Marca TODAS as URLs como pendentes. Use se pretender
  forçar o Google a re-indexar tudo desde o início.""",
        ),
        (
            "⑤ Settings",
            """\
As definições são por site. Selecione primeiro o site na lista.

• Track lastmod (ON/OFF)
    Quando ON, se o sitemap reportar uma nova data lastmod para uma URL,
    essa URL é automaticamente reposta como pendente no próximo run.
    Útil para blogs ou sites que atualizam o seu conteúdo frequentemente.

• Skip extensions
    Tipos de ficheiro a ignorar completamente (um por linha). A lista
    predefinida inclui imagens, PDFs, vídeos e arquivos:
      .jpg  .jpeg  .png  .gif  .webp  .svg  .pdf  .mp4  .zip

• Exclude patterns
    Se uma URL contiver alguma destas cadeias, é ignorada.
    Exemplo: adicionar "/tag/" ignorará todas as páginas de tags.

• Include patterns (lista branca)
    Se esta lista NÃO estiver vazia, apenas as URLs que contiverem
    pelo menos uma destas cadeias serão processadas. As restantes são ignoradas.
    Exemplo: adicionar "/blog/" processa apenas os artigos do blog.
    Nota: Exclude tem sempre prioridade sobre Include.

Clique em "Save settings" para aplicar as alterações.""",
        ),
        (
            "⑥ Multiplicar a quota diária",
            """\
O limite de 200 URLs/dia é por projeto GCP, não por conta de serviço.
Ao atribuir várias credenciais (de projetos GCP diferentes) a um site,
o SmartInstantIndex passa automaticamente para a seguinte quando a atual
esgota a sua quota diária.

Exemplo: 3 credenciais → 600 URLs/dia para o mesmo site.

COMO CONFIGURAR

Repita estes passos para cada projeto GCP adicional:

PASSO 1 — Criar um novo projeto GCP
  • Aceda a https://console.cloud.google.com
  • Clique no seletor de projeto → "Novo projeto"
  • Dê-lhe um nome e clique em "Criar"

PASSO 2 — Ativar a Web Search Indexing API
  • Na barra de pesquisa escreva "Web Search Indexing API"
  • Verifique que o novo projeto está selecionado no canto superior esquerdo
  • Clique nela → "ATIVAR"

PASSO 3 — Criar uma conta de serviço e transferir a chave
  • Menu → IAM e administração → Contas de serviço → "+ Criar conta de serviço"
  • Introduza um nome → "Criar e continuar" → "Concluído"
  • Clique na conta → separador "Chaves" → "Adicionar chave" → JSON → "Criar"
  • Guarde o ficheiro .json transferido na pasta da aplicação

PASSO 4 — Adicionar a conta de serviço ao Google Search Console
  • Copie o email da conta de serviço
  • Vá ao Search Console → a sua propriedade → Definições → Utilizadores
  • "Adicionar utilizador" → cole o email → função "Proprietário" → Adicionar
  • Pode adicionar várias contas de serviço à mesma propriedade

PASSO 5 — Atribuir as credenciais no SmartInstantIndex
  • Vá a Sites → edite o seu site
  • Clique em "+ Add credentials" e selecione o novo ficheiro .json
  • Repita para cada ficheiro de credenciais adicional
  • Clique em "Save"

O Dashboard mostra uma barra de progresso por credencial para ver
a quota utilizada por cada uma hoje.""",
        ),
    ],
    "Deutsch": [
        (
            "① Eine Website hinzufügen",
            """\
1. Klicken Sie in der Seitenleiste auf "Sites".

2. Füllen Sie das Formular aus:
   • Name — Eine kurze Kennung für Ihre Website (z. B. "meineseite"). Keine Leerzeichen.
   • Sitemap URL — Die vollständige URL Ihrer Sitemap, z. B.:
       https://beispiel.com/sitemap.xml
       https://beispiel.com/sitemap-index.xml
   • Credentials — Pfad zur JSON-Datei Ihres Google-Dienstkontos.
     Klicken Sie auf "Browse" (siehe Abschnitt ② für die Erstellung).
   • URLs file — Leer lassen. Die Datei wird automatisch als
     urls_{name}.json neben der App erstellt.

3. Klicken Sie auf "Save". Die Website erscheint in der Liste.""",
        ),
        (
            "② Google-Zugangsdaten — Schritt für Schritt",
            """\
Sie benötigen ein Google-Dienstkonto, um die Indexing API zu nutzen.

SCHRITT 1 — Google Cloud-Projekt erstellen
  • Gehen Sie zu https://console.cloud.google.com
  • Klicken Sie auf die Projektauswahl → "Neues Projekt"
  • Geben Sie einen Namen ein und klicken Sie auf "Erstellen"

SCHRITT 2 — Web Search Indexing API aktivieren
  • Geben Sie in der Suchleiste "Web Search Indexing API" ein
  • Prüfen Sie, ob das soeben erstellte Projekt im Quadrat oben links angezeigt wird.
    Falls nicht, klicken Sie darauf und wählen Sie es aus.
  • Klicken Sie darauf → klicken Sie auf "AKTIVIEREN"

SCHRITT 3 — Dienstkonto erstellen
  • Klicken Sie auf das Menü → Gehen Sie zu IAM & Verwaltung → Dienstkonten → "+ Erstellen"
  • Geben Sie einen Namen ein → "Erstellen und fortfahren" → "Fertig"
  • Klicken Sie auf das erstellte Konto → Registerkarte "Schlüssel"
  • "Schlüssel hinzufügen" → "Neuen Schlüssel erstellen" → JSON → "Erstellen"
  • Eine .json-Datei wird heruntergeladen. Benennen Sie sie in credentials_[ihrprojekt].json um
    und legen Sie sie in den gleichen Ordner wie die App (SmartInstantIndex.exe)

SCHRITT 4 — Dienstkonto zur Google Search Console hinzufügen
  • Kopieren Sie die E-Mail des Dienstkontos (z. B. name@projekt.iam.gserviceaccount.com)
  • Gehen Sie zu https://search.google.com/search-console
  • Wählen Sie Ihre Property → Einstellungen → Nutzer und Berechtigungen
  • "Nutzer hinzufügen" → E-Mail einfügen → Rolle "Inhaber" → Hinzufügen

SCHRITT 5 — Fertig!
  • Gehen Sie in SmartInstantIndex zu Sites → Browse → wählen Sie credentials.json

─────────────────────────────────────────
OPTIONAL — "Sync from GSC" aktivieren
─────────────────────────────────────────
Diese Funktion prüft, welche URLs tatsächlich in der Google Search Console indexiert sind,
und markiert sie automatisch. Sie erfordert einen zusätzlichen Schritt:

1. Aktivieren Sie im Google Cloud Console die API "Google Search Console API"
   (dieselben Schritte wie in SCHRITT 2, aber suchen Sie nach "Google Search Console API"):
   • Geben Sie in der Suchleiste "Google Search Console API" ein
   • Prüfen Sie, ob Ihr Projekt im Quadrat oben links angezeigt wird.
     Falls nicht, klicken Sie darauf und wählen Sie es aus.
   • Klicken Sie darauf → klicken Sie auf "AKTIVIEREN"

2. Füllen Sie in SmartInstantIndex → Sites das Feld "GSC Property URL" aus.
   Der Wert muss genau der Anzeige Ihrer Website in der Search Console entsprechen:

   • Domain-Property  →  sc-domain:beispiel.com
     (verwenden Sie dies, wenn Sie per DNS verifiziert haben — am häufigsten)

   • URL-Präfix-Property  →  https://beispiel.com/
     (verwenden Sie dies, wenn Sie per HTML-Datei oder Meta-Tag verifiziert haben)

   Typ prüfen: Öffnen Sie die Search Console und sehen Sie sich die Property-Liste
   links an — Domain-Properties haben ein Globus-Symbol,
   URL-Präfix-Properties haben ein Link-Symbol.""",
        ),
        (
            "③ Dashboard",
            """\
Das Dashboard ist Ihr Hauptsteuerungspanel.

• Website-Auswahl — Wählen Sie, mit welcher Website Sie arbeiten möchten.

• Statistikkarten:
    Total URLs   — Anzahl der URLs in Ihrer Sitemap.
    Indexed      — Bereits an Google übermittelte URLs.
    Pending      — Noch nicht übermittelte URLs.
    Quota left   — Wie viele URLs Sie heute noch einreichen können
                   (Google erlaubt max. 200 pro Tag und GCP-Projekt).

• Schaltfläche Run Indexing — Startet den Indexierungsprozess:
    1. Ruft Ihre Sitemap ab und synchronisiert neue/gelöschte URLs.
    2. Setzt URLs zurück, deren lastmod sich geändert hat (wenn Track lastmod ON).
    3. Übermittelt ausstehende URLs an Google bis zum Tageslimit.
    Fortschrittsbalken und Protokoll zeigen den Status in Echtzeit.

• Bei einem Credentials-Fehler prüfen Sie, ob credentials.json im gleichen
  Ordner wie die App liegt und ob der Pfad unter Sites korrekt ist.""",
        ),
        (
            "④ URLs-Panel",
            """\
Das URLs-Panel zeigt alle URLs Ihrer Sitemap und deren Status.

• Grün ✓ — URL wurde an Google übermittelt.
• Grau ✗ — URL ist ausstehend (wird beim nächsten Run übermittelt).

• Suchfeld — Geben Sie Text ein, um die Liste sofort zu filtern.

• Reset selected — Wählen Sie eine oder mehrere Zeilen aus (Strg+Klick
  oder Umschalt+Klick für mehrere) und klicken Sie, um sie als ausstehend
  zu markieren. Sie werden beim nächsten Run erneut übermittelt.

• Reset all — Markiert ALLE URLs als ausstehend. Verwenden Sie dies,
  wenn Google alles von Grund auf neu indexieren soll.""",
        ),
        (
            "⑤ Einstellungen (Settings)",
            """\
Einstellungen gelten pro Website. Wählen Sie zuerst die Website aus.

• Track lastmod (AN/AUS)
    Wenn AN, wird eine URL automatisch als ausstehend markiert, wenn
    die Sitemap ein neues lastmod-Datum meldet. Nützlich für Blogs oder
    Websites, die häufig Inhalte aktualisieren.

• Skip extensions
    Dateitypen, die vollständig ignoriert werden (einer pro Zeile).
    Die Standardliste enthält Bilder, PDFs, Videos und Archive:
      .jpg  .jpeg  .png  .gif  .webp  .svg  .pdf  .mp4  .zip

• Exclude patterns
    URLs, die einen dieser Strings enthalten, werden ignoriert.
    Beispiel: "/tag/" hinzufügen ignoriert alle Tag-Seiten.

• Include patterns (Whitelist)
    Wenn diese Liste NICHT leer ist, werden NUR URLs verarbeitet,
    die mindestens einen dieser Strings enthalten. Alle anderen werden ignoriert.
    Beispiel: "/blog/" hinzufügen verarbeitet nur Blog-Beiträge.
    Hinweis: Exclude hat immer Vorrang vor Include.

Klicken Sie auf "Save settings", um die Änderungen zu übernehmen.""",
        ),
        (
            "⑥ Tageslimit erhöhen",
            """\
Das Limit von 200 URLs/Tag gilt pro GCP-Projekt, nicht pro Dienstkonto.
Durch Zuweisung mehrerer Zugangsdaten (aus verschiedenen GCP-Projekten)
wechselt SmartInstantIndex automatisch zum nächsten, wenn das aktuelle
sein Tageslimit erreicht hat.

Beispiel: 3 Zugangsdateien → 600 URLs/Tag für dieselbe Website.

EINRICHTUNG

Wiederholen Sie diese Schritte für jedes zusätzliche GCP-Projekt:

SCHRITT 1 — Neues GCP-Projekt erstellen
  • Gehen Sie zu https://console.cloud.google.com
  • Klicken Sie auf die Projektauswahl → "Neues Projekt"
  • Geben Sie einen Namen ein und klicken Sie auf "Erstellen"

SCHRITT 2 — Web Search Indexing API aktivieren
  • Geben Sie in der Suchleiste "Web Search Indexing API" ein
  • Stellen Sie sicher, dass das neue Projekt oben links ausgewählt ist
  • Klicken Sie darauf → "AKTIVIEREN"

SCHRITT 3 — Dienstkonto erstellen und Schlüssel herunterladen
  • Menü → IAM & Verwaltung → Dienstkonten → "+ Erstellen"
  • Namen eingeben → "Erstellen und fortfahren" → "Fertig"
  • Konto anklicken → "Schlüssel" → "Schlüssel hinzufügen" → JSON → "Erstellen"
  • Die heruntergeladene .json-Datei in den App-Ordner legen

SCHRITT 4 — Dienstkonto zur Google Search Console hinzufügen
  • E-Mail des Dienstkontos kopieren
  • Search Console → Ihre Property → Einstellungen → Nutzer und Berechtigungen
  • "Nutzer hinzufügen" → E-Mail einfügen → Rolle "Inhaber" → Hinzufügen
  • Sie können mehrere Dienstkonten zur selben Property hinzufügen

SCHRITT 5 — Zugangsdaten in SmartInstantIndex zuweisen
  • Gehen Sie zu Sites → bearbeiten Sie Ihre Website
  • Klicken Sie auf "+ Add credentials" und wählen Sie die neue .json-Datei
  • Wiederholen Sie dies für jede weitere Zugangsdatei
  • Klicken Sie auf "Save"

Das Dashboard zeigt für jede Zugangsdatei einen Fortschrittsbalken,
der das heute verbrauchte Kontingent anzeigt.""",
        ),
    ],
}


# ─── Help Screen ─────────────────────────────────────────────────────────────

class HelpScreen(ctk.CTkFrame):
    LANGUAGES = ["English", "Español", "Français", "Português", "Deutsch"]

    def __init__(self, parent, app):
        super().__init__(parent, corner_radius=0)
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(self, text="Help", font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, padx=30, pady=(20, 10), sticky="w"
        )

        # Language selector
        lang_frame = ctk.CTkFrame(self)
        lang_frame.grid(row=1, column=0, padx=30, pady=5, sticky="w")
        ctk.CTkLabel(lang_frame, text="Language:").pack(side="left", padx=(0, 8))
        self.lang_var = ctk.StringVar(value="English")
        ctk.CTkOptionMenu(
            lang_frame, variable=self.lang_var, width=160,
            values=self.LANGUAGES,
            command=lambda _: self._render(),
        ).pack(side="left")

        # Single text area — one scrollbar, no nested scrollbars
        self.textbox = ctk.CTkTextbox(self, wrap="word")
        self.textbox.grid(row=2, column=0, padx=30, pady=(5, 20), sticky="nsew")
        self.textbox._textbox.tag_config("title", font=("", 13, "bold"), spacing1=14, spacing3=4)

        self._render()

    def on_show(self):
        pass  # content is static, no reload needed

    def _render(self):
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")

        lang = self.lang_var.get()
        sections = HELP_CONTENT.get(lang, HELP_CONTENT["English"])

        for i, (title, text) in enumerate(sections):
            if i > 0:
                self.textbox.insert("end", "\n")
            self.textbox._textbox.insert("end", title + "\n", "title")
            self.textbox.insert("end", text + "\n")

        self.textbox.configure(state="disabled")


# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = App()
    app.mainloop()
