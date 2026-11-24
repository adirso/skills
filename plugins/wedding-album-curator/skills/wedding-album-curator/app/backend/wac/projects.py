"""Project registry and native folder picker."""
from __future__ import annotations

import json
import platform
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from . import config
from .jobs import JobManager
from .pipeline import Project
from .scanner import validate_source_dir


class ProjectRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._open: dict[str, tuple[Project, JobManager]] = {}

    @property
    def index_file(self) -> Path:
        return config.data_dir() / "projects.json"

    def _read(self) -> list[dict]:
        if not self.index_file.exists():
            return []
        try:
            return json.loads(self.index_file.read_text())
        except json.JSONDecodeError:
            return []

    def _write(self, items: list[dict]) -> None:
        tmp = self.index_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(items, indent=2, ensure_ascii=False))
        tmp.replace(self.index_file)

    def list(self) -> list[dict]:
        out = []
        for p in self._read():
            p = dict(p)
            p["source_available"] = Path(p["source_dir"]).is_dir()
            out.append(p)
        return out

    def create(self, name: str, source_dir: str) -> dict:
        src = validate_source_dir(source_dir)
        name = (name or src.name).strip()[:120] or "Wedding"
        with self._lock:
            items = self._read()
            pid = uuid.uuid4().hex[:12]
            entry = {"id": pid, "name": name, "source_dir": str(src), "created_at": time.time()}
            items.append(entry)
            self._write(items)
        return entry

    def get(self, pid: str) -> tuple[Project, JobManager]:
        with self._lock:
            if pid in self._open:
                return self._open[pid]
            entry = next((p for p in self._read() if p["id"] == pid), None)
            if entry is None:
                raise KeyError(pid)
            proj = Project(pid, entry["name"], Path(entry["source_dir"]), config.projects_dir() / pid)
            jm = JobManager(proj.db)
            self._open[pid] = (proj, jm)
            return proj, jm

    def rename(self, pid: str, name: str) -> None:
        with self._lock:
            items = self._read()
            for p in items:
                if p["id"] == pid:
                    p["name"] = name.strip()[:120]
            self._write(items)

    def delete(self, pid: str) -> None:
        """Delete the project's local data (database, caches). Original photos are never touched."""
        with self._lock:
            items = [p for p in self._read() if p["id"] != pid]
            self._write(items)
            self._open.pop(pid, None)
            root = (config.projects_dir() / pid).resolve()
            if root.parent == config.projects_dir().resolve() and root.exists():
                shutil.rmtree(root)


def pick_folder(prompt: str = "Choose the folder with your wedding photos") -> Optional[str]:
    """Open the operating system's native folder chooser on the local machine."""
    system = platform.system()
    try:
        if system == "Darwin":
            script = f'POSIX path of (choose folder with prompt "{prompt}")'
            out = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=600)
            return out.stdout.strip() or None if out.returncode == 0 else None
        if system == "Windows":
            ps = ("Add-Type -AssemblyName System.Windows.Forms;"
                  "$d=New-Object System.Windows.Forms.FolderBrowserDialog;"
                  f"$d.Description='{prompt}';"
                  "if($d.ShowDialog() -eq 'OK'){Write-Output $d.SelectedPath}")
            out = subprocess.run(["powershell", "-NoProfile", "-STA", "-Command", ps], capture_output=True, text=True, timeout=600)
            return out.stdout.strip() or None
        for cmd in (["zenity", "--file-selection", "--directory", f"--title={prompt}"],
                    ["kdialog", "--getexistingdirectory", str(Path.home())]):
            if shutil.which(cmd[0]):
                out = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
                return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None
    return None


registry = ProjectRegistry()
