from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .tasks import process_generation_job


def spawn_job_process(project_root: Path, job_id: int) -> None:
    try:
        process_generation_job.delay(job_id)
        return
    except Exception:
        try:
            subprocess.Popen(
                [sys.executable, "manage.py", "run_job", str(job_id)],
                cwd=project_root,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception as exc:
            raise RuntimeError(
                "Não foi possível iniciar o processamento em segundo plano."
            ) from exc
