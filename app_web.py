"""
SmartInstantIndex — Local Web App
Starts FastAPI on localhost:7842, opens the browser, and shows a tray icon.
Clicking "Quit" in the tray menu shuts down the server and exits.
"""
import sys
import os
import threading
import webbrowser

# ── Paths ──────────────────────────────────────────────────────────────────────
if getattr(sys, "frozen", False):
    DATA_DIR = os.path.dirname(sys.executable)
    STATIC_DIR = os.path.join(sys._MEIPASS, "static")          # type: ignore
    ICON_PATH = os.path.join(sys._MEIPASS, "android-chrome-192x192.png")  # type: ignore
else:
    DATA_DIR = os.path.dirname(os.path.abspath(__file__))
    STATIC_DIR = os.path.join(DATA_DIR, "web_local", "frontend", "dist")
    ICON_PATH = os.path.join(DATA_DIR, "web_local", "frontend", "public", "android-chrome-192x192.png")

os.chdir(DATA_DIR)
os.environ["SMARTINDEX_DATA_DIR"] = DATA_DIR
os.environ["SMARTINDEX_STATIC_DIR"] = STATIC_DIR

PORT = 7842


def open_browser():
    webbrowser.open(f"http://localhost:{PORT}")


def run_server():
    import uvicorn
    from web_local.backend.routes import app
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=PORT,
        log_level="warning",
    )


def build_tray_icon():
    from PIL import Image
    import pystray

    image = Image.open(ICON_PATH)

    def on_open(_icon, _item):
        webbrowser.open(f"http://localhost:{PORT}")

    def on_quit(icon, _item):
        icon.stop()
        os._exit(0)

    menu = pystray.Menu(
        pystray.MenuItem("Open SmartInstantIndex", on_open, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", on_quit),
    )
    return pystray.Icon("SmartInstantIndex", image, "SmartInstantIndex", menu)


if __name__ == "__main__":
    # Start uvicorn in a background daemon thread
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    # Open browser after a short delay
    threading.Timer(1.2, open_browser).start()

    # Run tray icon on the main thread (required on macOS and Windows)
    icon = build_tray_icon()
    icon.run()
