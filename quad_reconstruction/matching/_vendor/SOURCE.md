# Vendored NetworkX Blossom Source

- Upstream project: NetworkX
- Upstream version: 3.6.1
- Source file: `networkx/algorithms/matching.py`
- Function: `max_weight_matching`
- Upstream URL: https://github.com/networkx/networkx/tree/networkx-3.6.1
- License: BSD-3-Clause, reproduced in `LICENSE.NetworkX.txt`
- Retrieved from the locally installed `networkx==3.6.1` package on 2026-08-11.

Local adaptation is intentionally narrow: NetworkX dispatch decorators were removed,
`repeat` is imported locally, and `matching_dict_to_set` is included without the
NetworkX-specific exception type. The blossom algorithm body is otherwise retained.
The LC Workflow Helper uses a small deterministic undirected graph adapter and has no
runtime dependency on NetworkX.
