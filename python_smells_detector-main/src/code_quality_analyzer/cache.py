"""Content-addressed analysis cache for the change-aware delta engine.

The Performance NFR requires that incremental analysis stay a small fraction
of a full project analysis.  The expensive part of ``pyexamine-delta`` is the
detectors re-parsing and re-walking every file in the head (and, in checkout
mode, base) snapshot, even though a pull request usually leaves the vast
majority of files untouched.

This module memoises the *result of analysing one tree* against the tree's
content.  A tree is identified by a manifest: the sorted list of
``(relative path, sha256)`` pairs of every Python file the detectors see.  Two
snapshots with byte-identical sources therefore share one cache entry, no
matter which temporary worktree directory they were materialised into (the
base and head worktrees, and repeated CI runs, all land in different
directories).

Correctness is by construction, not by approximation:

- Findings are stored with *relative* paths and re-rooted onto the tree being
  served on load, so a cache hit never returns paths pointing at a deleted
  worktree.
- The cache key also folds in a digest of the effective thresholds and the
  tool version, so a config change or an upgraded detector invalidates the
  entry instead of returning stale numbers.

Scope note (see ``docs/adr/ADR-008-performance-incremental-cache.md``): the
cache is a whole-tree memo, not per-file partial reuse.  Cross-file smells
(Dead Code, Data Clumps, architectural cycles, fan-in/out ...) make "re-analyse
only the changed files" unsafe without a detector-level refactor, so the memo
deliberately stays a pure function of tree content.  It already removes the
dominant repeated work: re-running the gate on unchanged sources, and the
base snapshot that is identical across every pull request of a repository.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Dict, List, Optional, Tuple

from .finding import Finding
from .fingerprint import relative_path

CACHE_SCHEMA_VERSION = 1
DEFAULT_CACHE_DIRNAME = ".pyexamine-cache"

# Effective-threshold sections that change detector output.  The cache must
# miss whenever any of them changes.
_THRESHOLD_SECTIONS = ("code_smells", "structural_smells", "architectural_smells")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_digest(path: str) -> str:
    """SHA-256 of a file's raw bytes, read in chunks so large trees stay cheap."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_manifest(root: str, ignore) -> Tuple[List[Tuple[str, str]], str]:
    """Sorted ``(relative path, sha256)`` pairs plus the manifest digest.

    ``ignore`` is a set of directory *names* to skip.  The walk deliberately
    mirrors the code-detector loop in ``delta.analyze_tree`` (it does not skip
    hidden directories beyond ``ignore``) so the manifest changes whenever the
    set of files any detector can observe changes.
    """
    entries: List[Tuple[str, str]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ignore]
        for name in filenames:
            if name.endswith(".py"):
                file_path = os.path.join(dirpath, name)
                entries.append((relative_path(file_path, root), file_digest(file_path)))
    entries.sort()
    digest = _sha256(json.dumps(entries, separators=(",", ":")))
    return entries, digest


def config_digest(config_handler) -> str:
    """Digest of every threshold that changes detector output."""
    sections = {
        section: config_handler.get_thresholds(section)
        for section in _THRESHOLD_SECTIONS
    }
    return _sha256(json.dumps(sections, sort_keys=True, default=str))


def _finding_to_record(finding: Finding, root: str) -> dict:
    return {
        "category": finding.category,
        "type": finding.smell_type,
        "file": relative_path(finding.file_path, root),
        "symbol": finding.symbol,
        "line": finding.line,
        "severity": finding.severity,
        "description": finding.description,
        "metric": finding.metric_value,
    }


def _record_to_finding(record: dict, root: str) -> Finding:
    rel = record.get("file") or ""
    # ``rel`` is "." for findings that describe the tree itself (a
    # module-level smell records the analysed directory as its file_path in
    # ``Finding``); joining it would yield "<root>/.", which changes the
    # SARIF fingerprint and turns one finding into NEW + RESOLVED on the next
    # run.  Map both the empty and the "." relative path back to the root.
    if not rel or rel == ".":
        file_path = root
    else:
        file_path = os.path.join(root, rel.replace("/", os.sep))
    return Finding(
        category=record.get("category") or "code",
        smell_type=record.get("type") or "",
        file_path=file_path,
        symbol=record.get("symbol") or "",
        line=record.get("line"),
        severity=record.get("severity") or "medium",
        description=record.get("description") or "",
        metric_value=record.get("metric"),
    )


class AnalysisCache:
    """A persistent, content-addressed store of per-tree analysis results."""

    def __init__(self, cache_dir: str):
        self.cache_dir = cache_dir

    def key_for(self, config_handler, manifest_digest: str, tool_version: str) -> str:
        return _sha256(
            "\x00".join(
                [
                    str(CACHE_SCHEMA_VERSION),
                    manifest_digest,
                    config_digest(config_handler),
                    tool_version or "unknown",
                ]
            )
        )

    def _entry_path(self, key: str) -> str:
        return os.path.join(self.cache_dir, key + ".json")

    def load(self, key: str, tree_root: str) -> Optional[Tuple[List[Finding], Dict[str, int]]]:
        """Cached findings re-rooted onto ``tree_root``, or ``None`` on a miss."""
        path = self._entry_path(key)
        if not os.path.isfile(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError):
            return None
        if payload.get("schema_version") != CACHE_SCHEMA_VERSION:
            return None
        findings = [
            _record_to_finding(record, tree_root)
            for record in payload.get("findings", [])
        ]
        fan_in = payload.get("fan_in") or {}
        return findings, fan_in

    def store(
        self,
        key: str,
        findings: List[Finding],
        fan_in: Dict[str, int],
        tree_root: str,
    ) -> None:
        """Write an entry atomically (LF endings, UTF-8)."""
        payload = {
            "schema_version": CACHE_SCHEMA_VERSION,
            "key": key,
            "findings": [_finding_to_record(finding, tree_root) for finding in findings],
            "fan_in": fan_in,
        }
        directory = os.path.dirname(os.path.abspath(self._entry_path(key)))
        if directory:
            os.makedirs(directory, exist_ok=True)
        text = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
        tmp_path = self._entry_path(key) + ".tmp"
        with open(tmp_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(tmp_path, self._entry_path(key))
