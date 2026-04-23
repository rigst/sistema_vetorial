from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def spawn_job_process(project_root: Path, job_id: int) -> None:
    subprocess.Popen(
        [str(project_root / ".venv/bin/python"), "manage.py", "run_job", str(job_id)],
        cwd=project_root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
