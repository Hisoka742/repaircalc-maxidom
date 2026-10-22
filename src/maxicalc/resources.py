"""Timing and resource log for the pipeline steps (laptop-first: CPU, RAM, optional GPU).

    with Stage("train") as st: ...      # st.seconds, st.peak_rss_mb, st.cpu_percent
    machine()                           # CPU model / cores / RAM / GPU name (torch + CUDA)

Used by the reproducibility run and the pitch metrics; numbers are measured, never estimated.
"""
import os
import platform
import threading
import time
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any

import psutil


def machine() -> dict[str, Any]:
    info: dict[str, Any] = {
        "cpu": platform.processor() or platform.machine(),
        "cores_logical": psutil.cpu_count(logical=True),
        "cores_physical": psutil.cpu_count(logical=False),
        "ram_gb": round(psutil.virtual_memory().total / 2**30, 1),
        "os": f"{platform.system()} {platform.release()}",
        "python": platform.python_version(), "gpu": None,
    }
    try:
        import torch

        if torch.cuda.is_available():
            info["gpu"] = torch.cuda.get_device_name(0)
    except Exception:
        pass
    return info


@dataclass
class Stage:
    name: str
    seconds: float = 0.0
    peak_rss_mb: float = 0.0
    cpu_percent: float = 0.0
    items: int = 0
    _t0: float = field(default=0.0, repr=False)
    _stop: threading.Event = field(default_factory=threading.Event, repr=False)

    def __enter__(self) -> "Stage":
        self._proc = psutil.Process(os.getpid())
        self._proc.cpu_percent(None)
        self._t0 = time.perf_counter()
        self.peak_rss_mb = self._proc.memory_info().rss / 2**20

        def watch() -> None:
            while not self._stop.wait(0.2):
                rss = self._proc.memory_info().rss / 2**20
                self.peak_rss_mb = max(self.peak_rss_mb, rss)

        self._th = threading.Thread(target=watch, daemon=True)
        self._th.start()
        return self

    def __exit__(self, et: type[BaseException] | None, ev: BaseException | None,
                 tb: TracebackType | None) -> None:
        self.seconds = time.perf_counter() - self._t0
        self._stop.set()
        self._th.join(timeout=1)
        # share of one core used on average over the stage (can exceed 100 with several cores)
        self.cpu_percent = self._proc.cpu_percent(None)

    def per_1k(self) -> float:
        return self.seconds / self.items * 1000 if self.items else 0.0
