"""Reader/writer for background-job records (TOML format), one file per job
under <workspace>/.sciqlop-jobs/<id>.toml.

Job format::

    [job]
    id = "a1b2c3d4e5f6"
    name = "11-year MMS build"
    command = "python build_survey.py"
    pid = 12345
    log_path = "/path/to/.sciqlop-jobs/a1b2c3d4e5f6.log"
    marker_path = "/path/to/.sciqlop-jobs/a1b2c3d4e5f6.exit"
    submitted_at = "2026-07-02T10:00:00"
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional


@dataclass
class Job:
    id: str
    name: str
    command: str
    pid: int
    log_path: str
    marker_path: str
    submitted_at: str

    @classmethod
    def load(cls, path: Path | str) -> "Job":
        path = Path(path)
        with open(path, "rb") as f:
            data = tomllib.load(f)
        j = data["job"]
        return cls(id=j["id"], name=j["name"], command=j["command"], pid=j["pid"],
                   log_path=j["log_path"], marker_path=j["marker_path"],
                   submitted_at=j["submitted_at"])

    def save(self, path: Path | str) -> None:
        import tomli_w
        data = {"job": {
            "id": self.id, "name": self.name, "command": self.command,
            "pid": self.pid, "log_path": self.log_path,
            "marker_path": self.marker_path, "submitted_at": self.submitted_at,
        }}
        with open(path, "wb") as f:
            tomli_w.dump(data, f)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def compute_status(marker_path: str, pid: int,
                   pid_alive: Callable[[int], bool] = _pid_alive) -> dict:
    marker = Path(marker_path)
    if marker.exists():
        try:
            exit_code: Optional[int] = int(marker.read_text().strip())
        except ValueError:
            exit_code = None
        finished_at = datetime.fromtimestamp(marker.stat().st_mtime).isoformat()
        return {"status": "done", "exit_code": exit_code, "finished_at": finished_at}
    if pid_alive(pid):
        return {"status": "running", "exit_code": None, "finished_at": None}
    return {"status": "crashed", "exit_code": None, "finished_at": None}
