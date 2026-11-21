"""Run the API and the bundled React app in one terminal."""
import getpass
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener
import webbrowser

from dotenv import dotenv_values, set_key

ROOT = Path(__file__).resolve().parents[1]
FRONT = ROOT / "frontend"
BACK = ROOT / "backend"
API = "http://127.0.0.1:8000"
UI = "http://localhost:3000"


def backend_environment():
    config = ROOT / ".env"
    if not config.exists():
        shutil.copyfile(ROOT / ".env.example", config)
    env = {**{k: v for k, v in dotenv_values(config).items() if v is not None}, **os.environ}
    keys = [k.strip() for k in env.get("LLM_API_KEYS", "").split(",") if k.strip()]
    if len(set(keys)) < 2 or any(k.startswith("replace-with-") for k in keys):
        print("Live chat needs two distinct provider keys. Enter them to save in .env, or press Ctrl+C to exit.")
        while True:
            keys = [getpass.getpass(f"API key {i} (hidden): ").strip() for i in (1, 2)]
            if all(keys) and len(set(keys)) == 2 and all("," not in k for k in keys):
                break
            print("Enter two different, non-empty keys without commas.")
        env["LLM_API_KEYS"] = ",".join(keys)
        set_key(str(config), "LLM_API_KEYS", env["LLM_API_KEYS"])
    if env.get("DATABASE_URL") == "sqlite:////data/app.db":
        env["DATABASE_URL"] = "sqlite:///./data/app.db"
    return env


def ensure_alive(children):
    for name, process in children:
        if process.poll() is not None:
            raise RuntimeError(f"{name} exited with code {process.returncode}. See its output above.")


def wait_for_service(url, children, *, health=False):
    local = build_opener(ProxyHandler({}))
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        ensure_alive(children)
        try:
            with local.open(url, timeout=2) as response:
                if response.status == 200 and (not health or json.load(response).get("status") == "ok"):
                    return
        except (URLError, TimeoutError, ConnectionError, ValueError):
            pass
        time.sleep(.3)
    raise RuntimeError(f"Timed out waiting for {url}. Check the service output above.")


def run():
    for port in (8000, 3000):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            if os.name == "nt":
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            else:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(("127.0.0.1", port))
            except OSError as exc:
                raise RuntimeError(f"Cannot use local port {port}: {exc}. Check whether another app is using it.") from exc
    env = backend_environment()
    site = FRONT / "local-ui"
    if not (site / "index.html").is_file():
        raise RuntimeError("Bundled interface missing. Extract the entire ZIP before running run.cmd.")
    children = []
    try:
        print("Starting backend on port 8000...", flush=True)
        backend = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1",
                                    "--port", "8000"], cwd=BACK, env=env)
        children.append(("Backend", backend))
        wait_for_service(API + "/health", children, health=True)
        print("Starting chat interface on port 3000...", flush=True)
        frontend = subprocess.Popen([sys.executable, "-m", "http.server", "3000",
                                     "--bind", "127.0.0.1", "--directory", str(site)], cwd=site)
        children.append(("Frontend", frontend))
        wait_for_service("http://127.0.0.1:3000", children)
        print(f"Open {UI}  |  API health: {API}/health\nPress Ctrl+C here to stop both services.", flush=True)
        webbrowser.open(UI)
        while True:
            ensure_alive(children)
            time.sleep(.5)
    finally:
        for _, child in reversed(children):
            if child.poll() is None:
                child.terminate()
        for _, child in children:
            try:
                child.wait(5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\nStopped.")
    except (OSError, RuntimeError, subprocess.CalledProcessError, EOFError) as exc:
        sys.exit(f"Startup stopped: {exc}")
