import subprocess

subprocess.run([
    "pyinstaller", "--onefile", "--windowed",
    "--name", "SmartInstantIndex", "app.py"
], check=True)
