# Solver Decision Record

## Decision

LC Workflow Helper vendors the `max_weight_matching` blossom implementation from
NetworkX 3.6.1 and exposes it through the addon's dependency-free matching interface.
The upstream BSD-3-Clause license and source record are shipped in `_vendor/`.

## Why Blossom

Triangle-pair candidates form a general graph. Odd cycles occur in practical meshes,
so bipartite matching and plain augmenting-path search cannot prove maximum cardinality.
Edmonds blossom provides maximum-cardinality, maximum-weight matching for these graphs.

## Objective Encoding

Each region is solved independently. Hard-invalid candidates never enter the graph.
Floating costs are converted to deterministic fixed-point integers. With cardinality
handled by `maxcardinality=True`, the encoded penalty is lexicographic:

1. normalized total candidate cost;
2. attribute-relaxation count;
3. valence and flow penalty;
4. stable candidate rank derived from source face/edge indices.

Input nodes, neighbors and edges are sorted. This makes repeated runs deterministic.

## Routing

- `Exact Blossom` solves regions up to the configured triangle limit. Larger regions
  remain unresolved rather than silently using a heuristic.
- `Auto` uses exact blossom under the limit and deterministic Seed + Augment above it.
- `Seed + Augment` remains the dependency-free fallback and reports `exact=false`.
- `Native Baseline` is comparative only and never claims optimality.

## Rejected Alternatives

- Runtime NetworkX dependency: unavailable in standard Blender Python and too large to
  require solely for one solver.
- New compiled dependency: raises platform, signing and extension-distribution risk.
- Seed + Augment alone: safe and useful, but cannot prove optimality on general odd-cycle
  graphs without blossom contraction.

## License

NetworkX 3.6.1 is BSD-3-Clause. The vendored algorithm retains attribution and ships
the complete upstream license in `_vendor/LICENSE.NetworkX.txt`. No NetworkX import is
performed at addon runtime.
