"""Background jobs that run the real CLI (`python -m freight_audit ...` / unittest) as a
subprocess and stream its output. The browser therefore exercises exactly the same code
path as the terminal; nothing is re-implemented for the web.

Only one job runs at a time: the pipeline deletes and rewrites its output directory, and
heavy runs (full scale ~30 s) should not overlap.
"""
from __future__ import annotations

import itertools
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone

from freight_audit import config as C

from .datasets import NAME_RE, ROOT, BadRequest, Busy, mark_busy

MAX_VOLUME = {"carriers": 500, "shipments": 100_000, "invoices": 75_000}
_ids = itertools.count(1)
_jobs: dict[int, "Job"] = {}
_lock = threading.Lock()


class Job:
    def __init__(self, kind: str, argv: list[str], title: str, dataset: str | None):
        self.id = next(_ids)
        self.kind, self.argv, self.title, self.dataset = kind, argv, title, dataset
        self.status = "queued"
        self.log: list[str] = []
        self.returncode: int | None = None
        self.started = time.time()
        self.finished: float | None = None
        self.proc: subprocess.Popen | None = None
        self.cancelled = False

    def to_dict(self, log_from: int = 0) -> dict:
        return {"id": self.id, "kind": self.kind, "title": self.title, "dataset": self.dataset,
                "status": self.status, "returncode": self.returncode,
                "command": " ".join(["python"] + self.argv[1:]),
                "started_at": datetime.fromtimestamp(self.started, timezone.utc).isoformat(timespec="seconds"),
                "elapsed_s": round((self.finished or time.time()) - self.started, 1),
                "log_total": len(self.log), "log_from": log_from, "log": self.log[log_from:]}


def _dataset_name(scale: str, seed: int, custom: dict) -> str:
    name = scale
    if custom:
        name += "-custom-" + "-".join(f"{custom.get(k, getattr(C.SCALES[scale], k))}" for k in MAX_VOLUME)
    if seed != C.DEFAULT_SEED:
        name += f"-seed{seed}"
    return name


def build(body: dict) -> tuple[str, list[str], str, str | None]:
    kind = body.get("kind")
    py = sys.executable
    if kind == "tests":
        return kind, [py, "-u", "-m", "unittest", "discover", "-s", "tests", "-v"], "Unit + end-to-end tests", None
    scale = body.get("scale", "starter")
    if scale not in C.SCALES:
        raise BadRequest(f"scale must be one of {sorted(C.SCALES)}")
    try:
        seed = int(body.get("seed") or C.DEFAULT_SEED)
    except ValueError:
        raise BadRequest("seed must be an integer")
    if not 0 <= seed < 2**63:
        raise BadRequest("seed out of range")
    if kind == "repro":
        return kind, [py, "-u", "-m", "freight_audit", "repro", "--scale", scale, "--seed", str(seed)], \
            f"Reproducibility check ({scale}, seed {seed})", None
    if kind != "run":
        raise BadRequest("kind must be run, repro or tests")
    custom = {}
    for k, hi in MAX_VOLUME.items():
        v = body.get(k)
        if v not in (None, ""):
            try:
                v = int(v)
            except ValueError:
                raise BadRequest(f"{k} must be an integer")
            if not 1 <= v <= hi:
                raise BadRequest(f"{k} must be between 1 and {hi}")
            if v != getattr(C.SCALES[scale], k):
                custom[k] = v
    name = _dataset_name(scale, seed, custom)
    assert NAME_RE.match(name)
    argv = [py, "-u", "-m", "freight_audit", "run", "--scale", scale, "--seed", str(seed),
            "--out", str(ROOT / "output" / name)]
    for k, v in custom.items():
        argv += [f"--{k}", str(v)]
    return kind, argv, f"Generate + audit ({name})", name


def start(body: dict) -> dict:
    kind, argv, title, dataset = build(body)
    with _lock:
        if any(j.status in ("queued", "running") for j in _jobs.values()):
            raise Busy("another job is still running; wait for it to finish or cancel it")
        job = Job(kind, argv, title, dataset)
        _jobs[job.id] = job
        if dataset:
            mark_busy(dataset, True)   # before the thread starts: no read can race the delete
    threading.Thread(target=_run, args=(job,), daemon=True).start()
    return job.to_dict()


def _run(job: Job) -> None:
    try:
        env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
        job.proc = subprocess.Popen(job.argv, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding="utf-8", errors="replace", bufsize=1)
        job.status = "running"
        with job.proc.stdout:
            for line in job.proc.stdout:
                job.log.append(line.rstrip("\n"))
        job.returncode = job.proc.wait()
        job.status = "cancelled" if job.cancelled else ("succeeded" if job.returncode == 0 else "failed")
    except Exception as exc:  # surfaced to the UI rather than lost in a thread
        job.log.append(f"[web] job failed to start: {exc!r}")
        job.status = "failed"
    finally:
        job.finished = time.time()
        if job.dataset:
            mark_busy(job.dataset, False)


def get(job_id: int, log_from: int = 0) -> dict | None:
    job = _jobs.get(job_id)
    return job.to_dict(max(0, log_from)) if job else None


def all_jobs() -> list[dict]:
    return [j.to_dict(len(j.log)) | {"log_tail": j.log[-1:]} for j in sorted(_jobs.values(), key=lambda j: -j.id)]


def cancel(job_id: int) -> dict | None:
    job = _jobs.get(job_id)
    if not job:
        return None
    if job.proc and job.status == "running":
        job.cancelled = True
        job.proc.terminate()
    return job.to_dict(len(job.log))
