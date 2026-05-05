"""Test fixtures for kaos-graph.

Auto-downloads the FOLIO ontology on first use so the marketing-grade
benchmark / round-trip tests run in CI as well as locally.
"""

from __future__ import annotations

import hashlib
import os
import urllib.error
import urllib.request
from pathlib import Path

import pytest

# FOLIO is the public legal ontology published by Alea Institute / 273V at
# alea-institute/folio (CC-BY-4.0). The ``main`` branch is fine for unit
# benchmarking — we don't pin a SHA because the test only asserts gross
# shape (>1000 nodes, valid round-trip, top-PageRank stability post-load),
# not exact byte-equivalence. If a downstream test ever needs a deterministic
# fixture, switch this URL to a tag-pinned blob and verify ``_FOLIO_SHA256``.
_FOLIO_URL = "https://github.com/alea-institute/folio/raw/main/FOLIO.owl"
_FOLIO_PATH = Path("/tmp/FOLIO/FOLIO.owl")
_FOLIO_MIN_BYTES = 5 * 1024 * 1024  # 5 MiB sanity-check floor
_FOLIO_SHA256: str | None = None  # set when we pin a tag


def _download_folio(dest: Path) -> Path:
    """Fetch FOLIO.owl into ``dest`` if it isn't already present."""
    if dest.exists() and dest.stat().st_size >= _FOLIO_MIN_BYTES:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    # urlretrieve to a tmp path then atomic-rename so a partial download
    # does not poison the cache for parallel pytest workers.
    tmp = dest.with_suffix(".owl.partial")
    req = urllib.request.Request(
        _FOLIO_URL,
        headers={"User-Agent": "kaos-graph-tests/0.1.0a1"},
    )
    with urllib.request.urlopen(req, timeout=120) as r, tmp.open("wb") as out:
        while True:
            chunk = r.read(64 * 1024)
            if not chunk:
                break
            out.write(chunk)
    if tmp.stat().st_size < _FOLIO_MIN_BYTES:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(
            f"FOLIO download truncated ({tmp.stat().st_size} bytes); "
            f"expected >= {_FOLIO_MIN_BYTES}."
        )
    if _FOLIO_SHA256 is not None:
        digest = hashlib.sha256(tmp.read_bytes()).hexdigest()
        if digest != _FOLIO_SHA256:
            tmp.unlink(missing_ok=True)
            raise RuntimeError(f"FOLIO sha256 mismatch: got {digest}, expected {_FOLIO_SHA256}")
    tmp.replace(dest)
    return dest


@pytest.fixture(scope="session")
def folio_owl_path() -> Path:
    """Session-scoped path to FOLIO.owl, downloading it on first use.

    Skips the test cleanly if the network is unreachable AND the file is
    not pre-staged — CI hosts that block egress can pre-populate
    ``KAOS_GRAPH_FOLIO_PATH`` to point at a local mirror.
    """
    override = os.environ.get("KAOS_GRAPH_FOLIO_PATH")
    if override:
        path = Path(override)
        if not path.exists():
            pytest.skip(f"KAOS_GRAPH_FOLIO_PATH={path} does not exist")
        return path
    try:
        return _download_folio(_FOLIO_PATH)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        pytest.skip(f"FOLIO download unavailable: {exc}")
