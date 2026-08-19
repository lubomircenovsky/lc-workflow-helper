from __future__ import annotations

import importlib
import pickle
import sys
import traceback
import types
from pathlib import Path


def _bootstrap_package(module_root: str, addon_root: Path) -> None:
    parts = module_root.split(".")
    for index in range(1, len(parts) + 1):
        name = ".".join(parts[:index])
        if name in sys.modules:
            continue
        module = types.ModuleType(name)
        module.__path__ = [str(addon_root)] if index == len(parts) else []
        sys.modules[name] = module


def main() -> int:
    input_path = Path(sys.argv[-4])
    output_path = Path(sys.argv[-3])
    module_root = sys.argv[-2]
    addon_root = Path(sys.argv[-1])
    try:
        _bootstrap_package(module_root, addon_root)
        candidates_module = importlib.import_module(
            f"{module_root}.quad_reconstruction.candidates"
        )
        with input_path.open("rb") as handle:
            payload = pickle.load(handle)
        candidates = candidates_module.generate_candidates(
            payload["snapshot"],
            payload["regions"],
            payload["candidate_settings"],
        )
        result = {"ok": True, "candidates": candidates}
    except Exception as exc:
        result = {
            "ok": False,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }
    with output_path.open("wb") as handle:
        pickle.dump(result, handle, protocol=pickle.HIGHEST_PROTOCOL)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
