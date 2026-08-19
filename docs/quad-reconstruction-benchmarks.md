# Quad Reconstruction Benchmark Report

Date: 2026-08-11

Harness: `tests/blender/phase5_benchmark.py`

Fixture: open planar triangulated grids, Strict candidate rules, native seed plus deterministic Seed + Augment, eight alternating-cycle passes, surface validation enabled, subdivision validation disabled. Times are one local run per Blender version and are not cross-machine guarantees.

## Results

| Blender | Triangles | Candidates | Coverage | Snapshot | Audit | Regions | Candidates | Matching | Apply | Validate | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 4.5.8 LTS | 1,000 | 1,455 | 100% | 0.036s | 0.003s | 0.002s | 0.055s | 0.005s | 0.002s | 0.058s | 0.191s |
| 4.5.8 LTS | 10,000 | 14,858 | 100% | 0.306s | 0.027s | 0.032s | 0.571s | 0.067s | 0.016s | 0.664s | 2.009s |
| 4.5.8 LTS | 100,000 | 149,552 | 100% | 3.208s | 0.442s | 0.448s | 6.075s | 1.082s | 0.219s | 7.321s | 22.431s |
| 5.2.0 LTS | 1,000 | 1,455 | 100% | 0.031s | 0.003s | 0.002s | 0.055s | 0.005s | 0.002s | 0.059s | 0.186s |
| 5.2.0 LTS | 10,000 | 14,858 | 100% | 0.310s | 0.026s | 0.020s | 0.553s | 0.076s | 0.018s | 0.660s | 1.977s |
| 5.2.0 LTS | 100,000 | 149,552 | 100% | 3.272s | 0.337s | 0.369s | 5.896s | 1.162s | 0.231s | 7.258s | 22.532s |

All cases preserved the source fingerprint. Maximum sampled surface deviation was `5.960464477539063e-08`, consistent with floating-point BVH precision on the planar fixture. The fallback reports `solver_exact=false`; 100% fixture coverage is not a claim of general mathematical optimality.

## Production Fixture

Fixture: `test_qudrify.blend`, object `Eames Lounge Chair cushion.003`, 27,624 triangles, 41,244 candidates, Strict profile, Auto solver, subdivision validation disabled. The source fingerprint remained unchanged and both modes produced the same 13,751 matching pairs.

| Blender | Candidate mode | Workers | Candidate stage | Matching | Total |
|---|---|---:|---:|---:|---:|
| 4.5.8 LTS | Serial | 0 | 2.55s | 6.37s | 16.08s |
| 4.5.8 LTS | External processes | 2 | 3.79s | 6.42s | 17.78s |
| 5.2.0 LTS | External processes | 2 | 3.55s | 6.41s | 17.38s |

At this size, process startup and snapshot serialization cost more than parallel candidate scoring saves. The default worker threshold is therefore 50,000 triangles.

The second production object, `Eames Lounge Chair.060`, contains 107,980 triangles plus 26 existing quads and 97 pre-existing near-zero-area faces. After unsafe-face barrier support it completed in Blender 4.5.8 with two workers in 73.22s: 160,902 candidates, 53,496 matching pairs, 15.47s candidate stage, 29.12s matching, 7.32s application and 13.82s validation. The source fingerprint and unsafe-face signature remained unchanged.

## Performance Work Completed

- Boundary vertices and UV layer names are precomputed once instead of once per candidate.
- Region barriers are derived from incident face loops instead of rescanning every mesh edge per region.
- Candidate normalization is performed from each region's own candidate slice instead of rescanning all prior candidates.
- Alternating four-cycle optimization uses O(1) face-pair lookup and one transactionally safe swap per bounded pass.
- External candidate workers are available for inputs above a configurable threshold without allowing worker access to Blender data.
- Immutable audit/region/candidate results use a bounded fingerprint/settings LRU cache.
- Candidate scores are computed once; edge and adjacency access is indexed.

Peak native Blender memory was not measured reliably by the Python harness and remains a profiling follow-up for unusually attribute-heavy production meshes.
