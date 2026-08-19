from __future__ import annotations

import os
import pickle
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import replace
from pathlib import Path

import bpy


def _python_executable() -> Path:
    executable = Path(sys.prefix) / "bin" / ("python.exe" if os.name == "nt" else "python3")
    if not executable.is_file() and os.name != "nt":
        executable = Path(sys.prefix) / "bin" / "python"
    if not executable.is_file():
        raise RuntimeError(f"Blender Python executable was not found: {executable}")
    return executable


def _balanced_region_chunks(regions, worker_count: int):
    chunks = [[] for _index in range(min(worker_count, max(len(regions), 1)))]
    loads = [0 for _chunk in chunks]
    for region in sorted(regions, key=lambda item: (-len(item.face_indices), item.index)):
        target = min(range(len(chunks)), key=lambda index: (loads[index], index))
        chunks[target].append(region)
        loads[target] += len(region.face_indices)
    return tuple(tuple(sorted(chunk, key=lambda item: item.index)) for chunk in chunks if chunk)


class ParallelCandidateTask:
    """External-process candidate generation with no Blender API in workers."""

    def __init__(self, snapshot, regions, candidate_settings, worker_count: int) -> None:
        self.snapshot = snapshot
        self.regions = regions
        self.candidate_settings = candidate_settings
        self.worker_count = max(1, worker_count)
        self.temp_dir: Path | None = None
        self.processes: list[subprocess.Popen] = []
        self.outputs: list[Path] = []
        self.error_logs: list[Path] = []
        self._error_handles = []

    def start(self) -> None:
        addon_root = Path(__file__).resolve().parents[1]
        module_root = __package__.rsplit(".quad_reconstruction", 1)[0]
        worker_script = Path(__file__).with_name("parallel_worker.py")
        configured_temp = os.environ.get("LCW_PARALLEL_TEMP_DIR", "").strip()
        temp_parent = Path(configured_temp) if configured_temp else None
        if temp_parent is not None:
            temp_parent.mkdir(parents=True, exist_ok=True)
        temp_root = temp_parent or Path(tempfile.gettempdir())
        self.temp_dir = temp_root / f"lcw_aiq_parallel_{uuid.uuid4().hex}"
        self.temp_dir.mkdir(parents=True, exist_ok=False)
        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            for index, chunk in enumerate(
                _balanced_region_chunks(self.regions, self.worker_count)
            ):
                input_path = self.temp_dir / f"input_{index}.pickle"
                output_path = self.temp_dir / f"output_{index}.pickle"
                error_path = self.temp_dir / f"error_{index}.log"
                with input_path.open("wb") as handle:
                    pickle.dump(
                        {
                            "snapshot": self.snapshot,
                            "regions": chunk,
                            "candidate_settings": self.candidate_settings,
                        },
                        handle,
                        protocol=pickle.HIGHEST_PROTOCOL,
                    )
                error_handle = error_path.open("w", encoding="utf-8")
                self._error_handles.append(error_handle)
                process = subprocess.Popen(
                    [
                        str(_python_executable()),
                        str(worker_script),
                        str(input_path),
                        str(output_path),
                        module_root,
                        str(addon_root),
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=error_handle,
                    creationflags=creation_flags,
                )
                self.processes.append(process)
                self.outputs.append(output_path)
                self.error_logs.append(error_path)
        except Exception:
            self.cancel()
            raise

    def done(self) -> bool:
        return bool(self.processes) and all(process.poll() is not None for process in self.processes)

    def result(self):
        if not self.done():
            raise RuntimeError("Parallel candidate task is still running.")
        candidates = []
        errors = []
        for process, output_path, error_path in zip(
            self.processes,
            self.outputs,
            self.error_logs,
            strict=True,
        ):
            if output_path.is_file():
                with output_path.open("rb") as handle:
                    payload = pickle.load(handle)
                if payload.get("ok"):
                    candidates.extend(payload["candidates"])
                else:
                    errors.append(payload.get("traceback") or payload.get("error"))
            else:
                error_text = error_path.read_text(encoding="utf-8", errors="replace")
                errors.append(
                    f"Worker exited with code {process.returncode}: {error_text.strip()}"
                )
        if errors:
            raise RuntimeError("Parallel candidate generation failed:\n" + "\n".join(errors))
        ordered = sorted(
            candidates,
            key=lambda item: (
                item.region_index,
                item.dissolve_edge_index,
                item.face_indices,
            ),
        )
        return tuple(replace(candidate, index=index) for index, candidate in enumerate(ordered))

    def cleanup(self) -> None:
        for handle in self._error_handles:
            if not handle.closed:
                handle.close()
        self._error_handles.clear()
        if self.temp_dir is not None and self.temp_dir.is_dir():
            shutil.rmtree(self.temp_dir)
        self.temp_dir = None

    def cancel(self) -> None:
        for process in self.processes:
            if process.poll() is None:
                process.terminate()
        for process in self.processes:
            try:
                process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5.0)
        self.cleanup()
