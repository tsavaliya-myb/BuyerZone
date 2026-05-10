"""Gunicorn config — preloads CLIP in the master so workers share weights via COW."""

import os


def on_starting(server):
    # Pin BLAS/OMP to single-threaded before torch initialises so post-fork
    # workers don't inherit a broken thread pool.
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")

    import torch

    torch.set_num_threads(1)

    from app.core.clip import _load

    _load()
    server.log.info("clip_preloaded_in_master")
