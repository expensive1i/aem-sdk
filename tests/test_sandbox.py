from __future__ import annotations

import json
from pathlib import Path

import pytest

import aem


@pytest.fixture
def sandbox(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A fake notebook sandbox: /data with a manifest and one CSV, and /outputs."""
    data = tmp_path / "data"
    data.mkdir()
    (data / "visits.csv").write_text("age,positive\n31,1\n45,0\n", encoding="utf-8")
    (data / "risk.onnx").write_bytes(b"onnx")
    manifest = {
        "aem-demo/malaria-visits": {"kind": "dataset", "file": "visits.csv", "format": "csv"},
        "aem-demo/risk-model": {"kind": "model", "file": "risk.onnx"},
    }
    (data / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setenv("AEM_DATA_DIR", str(data))
    monkeypatch.setenv("AEM_OUTPUT_DIR", str(tmp_path / "outputs"))
    return data


def test_detects_the_sandbox(sandbox: Path) -> None:
    assert aem.in_sandbox()
    assert aem.list_datasets() == ["aem-demo/malaria-visits"]
    assert aem.list_models() == ["aem-demo/risk-model"]
    assert aem.model_path("aem-demo/risk-model").endswith("risk.onnx")


def test_unattached_model_lists_what_is_attached(sandbox: Path) -> None:
    with pytest.raises(KeyError, match="aem-demo/risk-model"):
        aem.model_path("nobody/nothing")


def test_load_data_reads_the_mounted_file(sandbox: Path) -> None:
    pd = pytest.importorskip("pandas")
    df = aem.load_data("aem-demo/malaria-visits")
    assert isinstance(df, pd.DataFrame) and list(df.columns) == ["age", "positive"] and len(df) == 2


def test_outside_a_notebook_the_helpers_explain_why(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AEM_DATA_DIR", str(tmp_path / "nowhere"))
    assert not aem.in_sandbox()
    with pytest.raises(aem.SandboxOnlyError, match="never\\s+leaves AEM"):
        aem.load_data("aem-demo/malaria-visits")


def test_save_model_refuses_unexportable_formats(sandbox: Path) -> None:
    with pytest.raises(TypeError, match="can't be exported"):
        aem.save_model(object(), "mystery")
