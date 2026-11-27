from pathlib import Path

import pytest
from benchmarks import run_benchmark as bench


def test_generation_preserves_nonempty_directory(tmp_path):
    note = tmp_path / ".keep"
    note.write_bytes(b"existing")
    with pytest.raises(SystemExit) as exc:
        bench.main(["--root", str(tmp_path)])
    assert exc.value.code == 2 and note.read_bytes() == b"existing"


def test_failed_changed_run_restores_bytes_and_preserves_neighbour(tmp_path, monkeypatch):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    source = corpus / "mod.py"
    original = b"# coding: utf-8\r\nx = 1"
    source.write_bytes(original)
    existing = tmp_path / "_bench_cache"
    existing.mkdir()
    note = existing / "notes"
    note.write_bytes(b"review")

    def detect(*args, **kwargs):
        if source.read_bytes() != original:
            raise RuntimeError("detector interrupted")
        return []

    monkeypatch.setattr(bench, "analyze_tree", detect)
    with pytest.raises(RuntimeError, match="interrupted"):
        bench.run(str(corpus), str(Path(bench.__file__).resolve().parents[1] / "code_quality_config.yaml"))
    assert source.read_bytes() == original and note.read_bytes() == b"review"
    assert set(tmp_path.iterdir()) == {existing, corpus}
