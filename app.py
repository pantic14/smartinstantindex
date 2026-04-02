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
)
from smartinstantindex.sitemaps import fetch_urls_from_sitemap_recursive
from smartinstantindex.indexing import index_url

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
        stats_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self.stat_labels = {}
        for col, key in enumerate(["Total URLs", "Indexed", "Pending", "Quota left"]):
            f = ctk.CTkFrame(stats_frame)
            f.grid(row=0, column=col, padx=10, pady=10, sticky="ew")
            ctk.CTkLabel(f, text=key, font=ctk.CTkFont(size=12)).pack(pady=(8, 0))
            lbl = ctk.CTkLabel(f, text="—", font=ctk.CTkFont(size=22, weight="bold"))
            lbl.pack(pady=(0, 8))
            self.stat_labels[key] = lbl

        # Run button + progress
        action_frame = ctk.CTkFrame(self)
        action_frame.grid(row=3, column=0, padx=30, pady=5, sticky="ew")
        self.run_btn = ctk.CTkButton(action_frame, text="Run Indexing", command=self._run)
        self.run_btn.pack(side="left", padx=10, pady=10)
        self.progress = ctk.CTkProgressBar(action_frame)
        self.progress.pack(side="left", fill="x", expand=True, padx=10, pady=10)
        self.progress.set(0)

        # Log area
        ctk.CTkLabel(self, text="Log", font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=4, column=0, padx=30, pady=(10, 0), sticky="w"
        )
        self.grid_rowconfigure(5, weight=1)
        self.log_box = ctk.CTkTextbox(self, state="disabled")
        self.log_box.grid(row=5, column=0, padx=30, pady=(5, 20), sticky="nsew")

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
            return

        urls = migrate_urls(load_json(data_path(site["urls_file"])))
        total = len(urls)
        indexed = sum(1 for e in urls.values() if e["indexed"])
        pending = total - indexed

        quota = load_json(QUOTA_FILE)
        entry = quota.get(site["credentials"], {})
        used = entry.get("used", 0) if entry.get("date") == str(date.today()) else 0
        quota_left = max(0, 200 - used)

        self.stat_labels["Total URLs"].configure(text=str(total))
        self.stat_labels["Indexed"].configure(text=str(indexed))
        self.stat_labels["Pending"].configure(text=str(pending))
        self.stat_labels["Quota left"].configure(text=str(quota_left))

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

            creds_path = data_path(site["credentials"])
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

            pending = [url for url, e in existing_urls.items() if not e["indexed"]][:200]
            self._log(f"Pending to index: {len(pending)}")

            indexed_count = 0
            total_pending = len(pending)
            for i, url in enumerate(pending, 1):
                self.after(0, self.progress.set, i / total_pending if total_pending else 1)
                try:
                    result = index_url(url, creds_path, i)
                    if result:
                        existing_urls[url]["indexed"] = True
                        existing_urls[url]["indexed_at"] = str(date.today())
                        indexed_count += 1
                        self._log(f"[{i}] OK: {url}")
                except Exception as e:
                    existing_urls[url]["indexed"] = False
                    self._log(f"[{i}] ERROR: {e}")
                    break

            # Single save and single quota write at the end of the run
            save_urls_to_file(existing_urls, data_path(site["urls_file"]))
            if indexed_count:
                update_quota_batch(site["credentials"], indexed_count)

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

        self._fetch_btn = ctk.CTkButton(top, text="Fetch URLs", width=100, command=self._fetch_urls)
        self._fetch_btn.grid(row=0, column=3, padx=(0, 6))
        ctk.CTkButton(top, text="Mark indexed", width=110, command=self._mark_selected_indexed).grid(row=0, column=4, padx=(0, 6))
        ctk.CTkButton(top, text="Reset selected", width=110, command=self._reset_selected).grid(row=0, column=5, padx=(0, 6))
        ctk.CTkButton(top, text="Reset all", width=90, command=self._reset_all).grid(row=0, column=6, padx=(0, 10))

        self._fetch_status = ctk.StringVar()
        ctk.CTkLabel(top, textvariable=self._fetch_status, font=ctk.CTkFont(size=11), text_color="#aaaaaa").grid(
            row=1, column=0, columnspan=7, padx=10, pady=(0, 6), sticky="w"
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
            columns=("url", "status", "lastmod", "submitted"),
            show="headings",
            selectmode="extended",
        )
        self.tree.heading("url", text="URL")
        self.tree.heading("status", text="Status")
        self.tree.heading("lastmod", text="lastmod")
        self.tree.heading("submitted", text="Submitted")
        self.tree.column("url", stretch=True, minwidth=200)
        self.tree.column("status", width=80, anchor="center", stretch=False)
        self.tree.column("lastmod", width=130, anchor="center", stretch=False)
        self.tree.column("submitted", width=130, anchor="center", stretch=False)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        self.tree.tag_configure("indexed", foreground="#4caf50")
        self.tree.tag_configure("pending", foreground="#aaaaaa")

        self._all_urls = {}
        self._loaded_site = None   # tracks which site is currently loaded
        self._debounce_id = None   # for search debounce

    def on_show(self):
        config = get_config()
        names = [s["name"] for s in config.get("sites", [])]
        self.site_dropdown.configure(values=names)
        if names and self.site_var.get() not in names:
            self.site_var.set(names[0])
            self._loaded_site = None  # force reload on site change
        self._load_urls()

    def _load_urls(self):
        current_site = self.site_var.get()
        if current_site == self._loaded_site:
            return  # already loaded — skip disk read
        config = get_config()
        site = next((s for s in config.get("sites", []) if s["name"] == current_site), None)
        self._all_urls = migrate_urls(load_json(data_path(site["urls_file"]))) if site else {}
        self._loaded_site = current_site
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
            self.tree.insert("", "end", iid=url, values=(url, status, entry.get("lastmod") or "—", entry.get("indexed_at") or "—"), tags=(tag,))

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

        fields = [("Name", "name"), ("Sitemap URL", "sitemap_url"), ("URLs file", "urls_file")]
        self.form_vars = {}
        for i, (label, key) in enumerate(fields, 1):
            ctk.CTkLabel(form, text=label).grid(row=i, column=0, padx=10, pady=4, sticky="e")
            var = ctk.StringVar()
            self.form_vars[key] = var
            ctk.CTkEntry(form, textvariable=var).grid(row=i, column=1, padx=10, pady=4, sticky="ew")

        ctk.CTkLabel(form, text="Credentials").grid(row=4, column=0, padx=10, pady=4, sticky="e")
        self.form_vars["credentials"] = ctk.StringVar()
        ctk.CTkEntry(form, textvariable=self.form_vars["credentials"]).grid(
            row=4, column=1, padx=10, pady=4, sticky="ew"
        )
        ctk.CTkButton(form, text="Browse", width=70,
                      command=self._pick_credentials).grid(row=4, column=2, padx=(0, 10))

        btn_frame = ctk.CTkFrame(form)
        btn_frame.grid(row=5, column=0, columnspan=3, pady=10)
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
            ctk.CTkLabel(row, text=f"{site['name']}  —  {site['sitemap_url']}", anchor="w").grid(
                row=0, column=0, padx=10, sticky="w"
            )
            ctk.CTkButton(row, text="Edit", width=60,
                          command=lambda idx=i: self._edit_site(idx)).grid(row=0, column=1, padx=4)
            ctk.CTkButton(row, text="Delete", width=60, fg_color="red", hover_color="#a00000",
                          command=lambda idx=i: self._delete_site(idx)).grid(row=0, column=2, padx=4)

    def _pick_credentials(self):
        path = filedialog.askopenfilename(
            title="Select credentials.json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir=DATA_DIR,
        )
        if path:
            self.form_vars["credentials"].set(os.path.relpath(path, DATA_DIR))

    def _clear_form(self):
        self._editing_index = None
        for var in self.form_vars.values():
            var.set("")

    def _edit_site(self, idx):
        config = get_config()
        site = config["sites"][idx]
        self._editing_index = idx
        self.form_vars["name"].set(site.get("name", ""))
        self.form_vars["sitemap_url"].set(site.get("sitemap_url", ""))
        self.form_vars["credentials"].set(site.get("credentials", "credentials.json"))
        self.form_vars["urls_file"].set(site.get("urls_file", ""))

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
            "credentials": self.form_vars["credentials"].get().strip() or "credentials.json",
            "urls_file": self.form_vars["urls_file"].get().strip() or f"urls_{name}.json",
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
        form.grid(row=2, column=0, padx=30, pady=10, sticky="ew")
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
  • In SmartInstantIndex, go to Sites → Browse → select your credentials.json""",
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

• Search box — Type any text to filter the list instantly.

• Reset selected — Select one or more rows (use Ctrl+click or
  Shift+click for multiple) then click this button to mark them as
  pending. They will be resubmitted on the next run.

• Reset all — Marks ALL URLs as pending. Use this if you want to
  force Google to re-index everything from scratch.""",
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
  • En SmartInstantIndex, ve a Sites → Browse → selecciona tu credentials.json""",
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

• Buscador — Escribe cualquier texto para filtrar la lista al instante.

• Reset selected — Selecciona una o varias filas (usa Ctrl+clic o
  Shift+clic para seleccionar varias) y haz clic en este botón para
  marcarlas como pendientes. Se reenviarán en el próximo run.

• Reset all — Marca TODAS las URLs como pendientes. Úsalo si quieres
  forzar a Google a re-indexar todo desde cero.""",
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
  • Dans SmartInstantIndex, allez dans Sites → Browse → sélectionnez credentials.json""",
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
  • No SmartInstantIndex, vá a Sites → Browse → selecione credentials.json""",
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
  • Gehen Sie in SmartInstantIndex zu Sites → Browse → wählen Sie credentials.json""",
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
