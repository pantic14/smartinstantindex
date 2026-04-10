import subprocess
import sys

sep = ";" if sys.platform == "win32" else ":"

subprocess.run([
    "pyinstaller",
    "--onefile",
    "--windowed",
    "--name", "SmartInstantIndex",
    "--add-data", f"web-local/frontend/dist{sep}static",
    "--add-data", f"web-local/frontend/public/android-chrome-192x192.png{sep}.",
    "--hidden-import", "uvicorn.lifespan.on",
    "--hidden-import", "uvicorn.lifespan.off",
    "--hidden-import", "uvicorn.protocols.http.auto",
    "--hidden-import", "uvicorn.protocols.websockets.auto",
    "--hidden-import", "uvicorn.loops.auto",
    "--hidden-import", "fastapi",
    "--hidden-import", "pystray",
    "--hidden-import", "PIL",
    "--hidden-import", "PIL.Image",
    "app_web.py",
], check=True)

