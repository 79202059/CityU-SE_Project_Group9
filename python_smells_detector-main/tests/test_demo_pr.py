"""Exercise the demo's normal CLI entry point against disposable directories."""

import importlib.util
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "demo_pr.py"
spec = importlib.util.spec_from_file_location("demo_pr", SCRIPT)
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


def test_nonempty_root_preserves_even_hidden_files(tmp_path, capsys):
    sentinel = tmp_path / ".keep"
    sentinel.write_bytes(b"original\x00contents")
    assert demo.main(["--root", str(tmp_path)]) == 2
    assert "not empty" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == [sentinel]
    assert sentinel.read_bytes() == b"original\x00contents"


def test_file_as_root_is_preserved(tmp_path):
    sentinel = tmp_path / "demo"
    sentinel.write_bytes(b"original")
    assert demo.main(["--root", str(sentinel)]) == 2
    assert sentinel.read_bytes() == b"original"


def test_link_to_empty_directory_is_rejected(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "alias"
    if os.name == "nt":
        subprocess.run(["cmd", "/d", "/c", "mklink", "/J", str(link), str(target)], check=True)
    else:
        link.symlink_to(target, target_is_directory=True)
    assert demo.main(["--root", str(link)]) == 2
    assert link.is_dir()
    assert list(target.iterdir()) == []


def test_git_directory_override_is_rejected_before_writing(tmp_path, monkeypatch):
    other = tmp_path / "outside"
    monkeypatch.setenv("GIT_DIR", str(other))
    assert demo.main(["--root", str(tmp_path / "demo")]) == 2
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("mode", ["default", "empty", "new"])
def test_walkthrough_and_directory_lifetime(tmp_path, monkeypatch, capsys, mode):
    monkeypatch.chdir(tmp_path)
    legacy_root = tmp_path / "demo" / "demo-pr"
    legacy_root.mkdir(parents=True)
    sentinel = legacy_root / "notes.txt"
    sentinel.write_bytes(b"keep")
    destination = tmp_path / "chosen"
    if mode == "empty":
        destination.mkdir()
    args = [] if mode == "default" else ["--root", str(destination)]
    assert demo.main(args) == 0
    lines = capsys.readouterr().out.splitlines()
    assert [line.split("exit=")[1].split()[0] for line in lines if "(expected " in line] == [
        "0", "1", "0",
    ]
    assert "reproduced: yes" in lines
    assert sentinel.read_bytes() == b"keep"
    root = Path(next(line.removeprefix("built a clean repository at ") for line in lines
                     if line.startswith("built a clean repository at ")))
    if mode == "default":
        assert not root.exists()
    else:
        assert root == destination
        assert (root / ".git").is_dir()
        head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"])
        assert demo.main(args) == 2
        assert subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"]) == head
