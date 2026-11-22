"""Automated file-watcher.

Watches data/landing/ with the `watchdog` library. When a new .csv/.xlsx appears it waits
until the file has finished being written (size stops changing), then calls the ingestion
API. Success -> file moves to data/archive/, failure -> data/rejected/ (+ a .error.txt).

We use watchdog's PollingObserver (checks the folder every 2 s) instead of the default
inotify observer, because inotify does not see files created on the host side of a
Docker bind mount on Mac/Windows.
"""
import shutil
import sys
import threading
import time
from pathlib import Path

import requests
from watchdog.events import FileSystemEventHandler
from watchdog.observers.polling import PollingObserver

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.config import ARCHIVE, INGEST_API_URL, LANDING, REJECTED  # noqa: E402

EXTENSIONS = {".csv", ".xlsx"}
STABLE_SECONDS = 3
SCAN_EVERY = 2


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def is_candidate(p: Path):
    return p.is_file() and p.suffix.lower() in EXTENSIONS and not p.name.startswith((".", "~$"))


class Handler(FileSystemEventHandler):
    def __init__(self, pending):
        self.pending, self.lock = pending, threading.Lock()

    def _add(self, path):
        p = Path(path)
        if is_candidate(p):
            with self.lock:
                if p not in self.pending:
                    log(f"detected {p.name}")
                self.pending.add(p)

    def on_created(self, event):
        if not event.is_directory:
            self._add(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self._add(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self._add(event.dest_path)


def ingest(path: Path):
    try:
        r = requests.post(f"{INGEST_API_URL}/ingest",
                          json={"file_path": str(path), "triggered_by": "watcher"}, timeout=3600)
    except requests.exceptions.ConnectionError:
        log(f"API not reachable yet - will retry {path.name}")
        return "retry"
    try:
        body = r.json()
    except ValueError:
        body = {"status": "failed", "error": r.text[:300]}
    status = body.get("status")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    if status in ("success", "skipped"):
        ARCHIVE.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), ARCHIVE / f"{stamp}__{path.name}")
        log(f"OK  {path.name}: {body.get('rows_loaded')} rows loaded, "
            f"{body.get('rows_rejected')} rejected in {body.get('duration_sec')}s ({status})")
    else:
        REJECTED.mkdir(parents=True, exist_ok=True)
        dest = REJECTED / f"{stamp}__{path.name}"
        shutil.move(str(path), dest)
        Path(str(dest) + ".error.txt").write_text(str(body))
        log(f"FAILED {path.name}: {body.get('error') or body.get('message')}")
    return status


def main():
    LANDING.mkdir(parents=True, exist_ok=True)
    pending, sizes = set(), {}
    handler = Handler(pending)
    for p in LANDING.iterdir():              # files already waiting when we start
        handler._add(p)
    observer = PollingObserver(timeout=SCAN_EVERY)
    observer.schedule(handler, str(LANDING), recursive=False)
    observer.start()
    log(f"watching {LANDING} -> {INGEST_API_URL}")
    try:
        while True:
            time.sleep(SCAN_EVERY)
            with handler.lock:
                candidates = [p for p in pending if p.exists()]
                pending.intersection_update(candidates)
            ready = []
            for p in candidates:
                st = p.stat()
                sig = (st.st_size, st.st_mtime)
                if sizes.get(p) == sig and time.time() - st.st_mtime >= STABLE_SECONDS:
                    ready.append(p)
                sizes[p] = sig
            for p in sorted(ready, key=lambda x: x.name):     # 01_ before 05_ before 06_
                result = ingest(p)
                if result != "retry":
                    with handler.lock:
                        pending.discard(p)
                    sizes.pop(p, None)
    finally:
        observer.stop()
        observer.join()


if __name__ == "__main__":
    main()
