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

        ctk.CTkButton(top, text="Reset selected", width=110, command=self._reset_selected).grid(row=0, column=3, padx=(0, 6))
        ctk.CTkButton(top, text="Reset all", width=90, command=self._reset_all).grid(row=0, column=4, padx=(0, 10))

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
            columns=("url", "status", "lastmod"),
            show="headings",
            selectmode="extended",
        )
        self.tree.heading("url", text="URL")
        self.tree.heading("status", text="Status")
        self.tree.heading("lastmod", text="lastmod")
        self.tree.column("url", stretch=True, minwidth=200)
        self.tree.column("status", width=80, anchor="center", stretch=False)
        self.tree.column("lastmod", width=130, anchor="center", stretch=False)

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
            self.tree.insert("", "end", iid=url, values=(url, status, entry.get("lastmod") or "—"), tags=(tag,))

    def _get_site(self):
        config = get_config()
        return next((s for s in config.get("sites", []) if s["name"] == self.site_var.get()), None)

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


# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = App()
    app.mainloop()
