"""Helpers that work inside an AEM notebook, where the data is.

Datasets and models attached to the notebook are mounted read-only; trained
models are saved to /outputs, the only writable folder, and leave the platform
through the export review. Outside a notebook these raise SandboxOnlyError.
"""

from __future__ import annotations

import json
import os
from typing import Any

from .errors import SandboxOnlyError

__all__ = ["in_sandbox", "list_datasets", "list_models", "load_data", "model_path", "save_model"]


def _data_dir() -> str:
    return os.environ.get("AEM_DATA_DIR", "/data")


def _output_dir() -> str:
    return os.environ.get("AEM_OUTPUT_DIR", "/outputs")


def in_sandbox() -> bool:
    """True when running inside an AEM notebook."""
    return os.path.exists(os.path.join(_data_dir(), "manifest.json"))


def _require_sandbox(what: str) -> None:
    if not in_sandbox():
        raise SandboxOnlyError(
            f"{what} only works inside an AEM notebook, where the data lives. Restricted data never "
            "leaves AEM, so from your own computer create a notebook and run your code there: "
            "client.notebooks.create(...), then client.notebooks.run(...)."
        )


def _manifest() -> dict[str, Any]:
    with open(os.path.join(_data_dir(), "manifest.json"), encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def _entries(kind: str) -> dict[str, Any]:
    return {name: e for name, e in _manifest().items() if e.get("kind", "dataset") == kind}


def list_datasets() -> list[str]:
    """Names of the datasets attached to this notebook."""
    _require_sandbox("list_datasets()")
    return sorted(_entries("dataset"))


def list_models() -> list[str]:
    """Names of the models attached to this notebook."""
    _require_sandbox("list_models()")
    return sorted(_entries("model"))


def model_path(name: str) -> str:
    """Path to an attached model's file (read-only).

    Load it with the framework it was saved in, for example
    onnxruntime.InferenceSession(path), torch.load(path) or joblib.load(path).
    """
    _require_sandbox("model_path()")
    models = _entries("model")
    if name not in models:
        attached = ", ".join(sorted(models)) or "none"
        raise KeyError(f"Model {name!r} is not attached to this notebook. Attached models: {attached}")
    return os.path.join(_data_dir(), models[name]["file"])


def load_data(name: str, **kwargs: Any) -> Any:
    """Load an attached dataset into a pandas DataFrame.

    Extra keyword arguments are passed to pandas.read_csv / read_parquet.
    """
    _require_sandbox("load_data()")
    import pandas as pd

    datasets = _entries("dataset")
    if name not in datasets:
        attached = ", ".join(sorted(datasets)) or "none"
        raise KeyError(f"Dataset {name!r} is not attached to this notebook. Attached datasets: {attached}")
    entry = datasets[name]
    path = os.path.join(_data_dir(), entry["file"])
    if entry.get("format") == "parquet":
        return pd.read_parquet(path, **kwargs)
    return pd.read_csv(path, **kwargs)


def _safe_name(name: str) -> str:
    keep = "".join(c if c.isalnum() or c in "-_." else "-" for c in name).strip(".-")
    if not keep:
        raise ValueError("Model name must contain letters or numbers")
    return keep


def save_model(model: Any, name: str, sample_input: Any = None) -> str:
    """Save a trained model to /outputs in an exportable format, and return its path.

    - PyTorch modules and dicts of tensors/arrays are saved as .safetensors
    - scikit-learn models are converted to .onnx (pass sample_input, or the
      model must expose n_features_in_)

    Other formats can't be exported because they could hide data or run code.
    """
    _require_sandbox("save_model()")
    name = _safe_name(name)
    out = _output_dir()
    os.makedirs(out, exist_ok=True)

    try:
        import torch

        if isinstance(model, torch.nn.Module):
            model = model.state_dict()
    except ImportError:
        torch = None

    if isinstance(model, dict):
        path = os.path.join(out, f"{name}.safetensors")
        if torch is not None and any(isinstance(v, torch.Tensor) for v in model.values()):
            from safetensors.torch import save_file as save_torch

            save_torch({k: v.contiguous() for k, v in model.items()}, path)
        else:
            import numpy as np
            from safetensors.numpy import save_file as save_numpy

            save_numpy({k: np.ascontiguousarray(v) for k, v in model.items()}, path)
        print(f"Saved {path}. Request an export to take it out of the sandbox.")
        return path

    if hasattr(model, "fit") and hasattr(model, "predict"):
        from skl2onnx import convert_sklearn
        from skl2onnx.common.data_types import FloatTensorType

        n_features = getattr(model, "n_features_in_", None)
        if sample_input is not None:
            n_features = len(sample_input[0])
        if n_features is None:
            raise ValueError("Pass sample_input so the model's input shape is known")
        onx = convert_sklearn(model, initial_types=[("input", FloatTensorType([None, int(n_features)]))])
        path = os.path.join(out, f"{name}.onnx")
        with open(path, "wb") as f:
            f.write(onx.SerializeToString())
        print(f"Saved {path}. Request an export to take it out of the sandbox.")
        return path

    raise TypeError(
        "save_model supports PyTorch modules, dicts of tensors/arrays, and scikit-learn models. "
        "Other formats can't be exported because they could hide data or run code."
    )
