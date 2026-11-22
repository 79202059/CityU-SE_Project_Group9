"""Materialise two git revisions as standalone working trees.

``pyexamine-delta`` needs to run the detectors against the *base* and *head*
snapshots of a repository.  The least invasive way to do that is ``git
worktree add``: it checks out a commit into a temporary directory without
touching the user's working tree.  The temporary worktrees are removed on
exit, even if analysis raises.
"""

import os
import shutil
import subprocess
import tempfile
from typing import List, Optional


class VersionProviderError(RuntimeError):
    """Raised when a git revision cannot be materialised."""


def resolve_repo_root(path: str, git_binary: str = "git") -> str:
    """Return the repository top-level directory containing ``path``."""
    try:
        out = subprocess.run(
            [git_binary, "-C", path, "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise VersionProviderError(
            f"Could not locate the git repository for '{path}': {exc}"
        ) from exc
    if not out:
        raise VersionProviderError(f"Could not locate the git repository for '{path}'")
    return os.path.abspath(out)


class VersionProvider:
    """Check out git refs into temporary working trees and clean them up."""

    def __init__(self, repo_root: str, git_binary: str = "git"):
        self.repo_root = os.path.abspath(repo_root)
        self.git_binary = git_binary
        self._worktrees: List[str] = []
        self._temp_dirs: List[str] = []

    def materialize(self, ref: str) -> str:
        """Check out ``ref`` into a fresh temporary worktree.

        Returns:
            Absolute path to the checked-out tree.
        """
        temp_dir = tempfile.mkdtemp(prefix="pyexamine-delta-")
        self._temp_dirs.append(temp_dir)
        worktree = os.path.join(temp_dir, "tree")
        try:
            subprocess.run(
                [
                    self.git_binary, "-C", self.repo_root,
                    "worktree", "add", "--detach", "--force",
                    worktree, ref,
                ],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            stderr = getattr(exc, "stderr", None)
            detail = stderr if isinstance(stderr, str) else str(exc)
            raise VersionProviderError(
                f"Failed to check out revision '{ref}': {detail}"
            ) from exc

        self._worktrees.append(worktree)
        return worktree

    def cleanup(self):
        """Remove temporary worktrees and their parent temp directories."""
        for worktree in self._worktrees:
            try:
                subprocess.run(
                    [self.git_binary, "-C", self.repo_root,
                     "worktree", "remove", "--force", worktree],
                    check=False,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
            except OSError:
                pass
        self._worktrees.clear()

        for temp_dir in self._temp_dirs:
            shutil.rmtree(temp_dir, ignore_errors=True)
        self._temp_dirs.clear()

    def __enter__(self) -> "VersionProvider":
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.cleanup()
        return False


def optional_ref(ref: Optional[str], fallback: str = "HEAD") -> str:
    """Normalise an optional ref argument to a concrete ref."""
    return ref or fallback
