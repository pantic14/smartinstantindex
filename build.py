import subprocess

subprocess.run([
    "pyinstaller", "--onefile", "--windowed",
    "--collect-all", "customtkinter",
    "--name", "SmartInstantIndex", "app.py"
], check=True)
