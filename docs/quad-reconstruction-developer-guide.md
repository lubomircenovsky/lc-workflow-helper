# Quad Reconstruction Developer Guide

## Architecture

`quad_reconstruction/` separates immutable pure-core data from Blender adapters:

- `models.py`: frozen snapshots, candidates, matching, validation and report models.
- `topology_snapshot.py`, `fingerprint.py`, `audit.py`, `regions.py`: source capture and safe decomposition.
- `candidates.py`, `scoring.py`: hard validation, robust median/MAD scaling and configurable costs.
- `matching/`: exact vendored blossom and deterministic seed/augment fallback.
- `reconstruction.py`, `validation.py`, `attributes.py`: Blender copies, dissolve-only application and checks.
- `cache.py`: bounded LRU of immutable audit/region/candidate results keyed by source fingerprint and settings.
- `parallel.py`, `parallel_worker.py`: cancellable external-process candidate generation over immutable snapshots.
- `jobs.py`, `operators.py`, `panels.py`: main-thread cooperative orchestration and UI.
- `reporting.py`, `confidence.py`: structured Text/JSON output and confidence.

The pure computation modules do not require active Blender context. Blender RNA and BMesh access remains on the main thread.

## Parallel Core Processing

Workers use Blender's bundled Python executable, but bootstrap only the pure `quad_reconstruction` package and never import the add-on entry point, `bpy`, or `bmesh`. Regions are assigned deterministically with largest-first load balancing. Inputs and outputs use per-run temporary pickle files, results are stably reindexed after merge, and cancellation terminates every process before deleting its temporary directory.

Parallelism is limited to candidate generation. Snapshot capture, native seed creation, matching application and validation stay on Blender's main thread. The default 50k triangle threshold reflects measured process startup and serialization overhead; it is a tuning control rather than a correctness setting.

## Safety Contract

1. Capture a canonical BLAKE2b source fingerprint before work.
2. Recheck it before output application and after validation.
3. Start from `object.copy()` plus `mesh.copy()`.
4. Dissolve only hard-valid, face-disjoint matched diagonals; never move vertices.
5. Roll back the complete output object when application or validation fails.
6. Mark each generated collection, object and mesh with a namespaced run ID.
7. Validate every marker and run ID before clear/cancel deletion.
8. Remove temporary subdivision objects and meshes in `finally`.

Degenerate and duplicate source faces are included in the audit but excluded from candidate edges. They form barrier-only regions so matching reports them as unresolved. Validation compares a canonical multiset of unsafe face vertex keys before and after reconstruction; only exact preservation is accepted.

The fingerprint covers positions, topology, loops, UV/attribute metadata and values, materials, transforms, parent reference, custom normals and modifier types. Tests compare it before and after Analyze, Reconstruct and Cancel.

## Advanced Validation

Surface deviation constructs source and output BVHs and samples used vertices, non-wire edge midpoints and polygon centers in both directions. Reports include maximum, mean, p50 and p95.

Subdivision validation creates a disposable output copy, removes inherited modifiers, evaluates one Catmull-Clark level and checks finite coordinates, degenerate faces and bounding-box change. It does not apply the modifier and always removes temporary data.

## Determinism

Candidates use stable source indices. Costs use region median/MAD normalization and stable tie-breaks. Exact weights are fixed-point integers. Report UUIDs and timestamps are metadata and are excluded from settings/result identity.

## Solver Decision and License

See `quad_reconstruction/matching/DECISION.md`. The exact implementation is adapted from NetworkX 3.6.1 `max_weight_matching` without a NetworkX runtime dependency. BSD-3-Clause attribution is preserved in `matching/_vendor/LICENSE.NetworkX.txt` and `SOURCE.md`.

## Tests

Pure tests:

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

Blender integration example:

```powershell
blender --background --factory-startup --python tests\blender\phase5_validation_smoke.py
```

Benchmark example:

```powershell
blender --background --factory-startup --python tests\blender\phase5_benchmark.py -- --sizes 1000,10000,100000
```

## Rollback

In Blender, use Undo immediately after a completed operator or use `Clear Generated Results` for the latest internally identified run. Cancellation performs the same guarded run cleanup.

Repository rollback must preserve unrelated user work. Before release, create a normal checkpoint commit. To discard this feature later, revert that feature commit with `git revert <commit>`; do not use `git reset --hard` on a shared or dirty worktree.
