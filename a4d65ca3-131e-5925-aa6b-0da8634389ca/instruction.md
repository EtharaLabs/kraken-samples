# Performance Optimization: `networkx/networkx` PR #7971

You are working in `/testbed`, a checkout of `networkx/networkx` at commit `aab0380830b6f21653bc1f88184e7ad4d1017888`.
The Python environment is a conda env named `testbed` (auto-activated in new shells via `~/.bashrc`).

## Problem statement

connected_components and weakly_connected_components perform redundant BFS traversals on nodes already assigned to components. On disconnected graphs with large components, the current implementation revisits the same nodes multiple times, leading to O(n*k) instead of O(n) behavior where k is the number of components.

## Your task

Modify source files under `/testbed` to improve runtime performance while preserving correctness.
The grader will:

1. Reset the repository to `harbor-base` and measure the **baseline** runtime with a hidden workload.
2. Reapply your changes, rebuild, and run the covering tests. These **must pass**.
3. Measure the **optimized** runtime with the same hidden workload.
4. Compute `speedup = baseline / optimized`. You **pass** iff `speedup >= 1.02` and the covering tests pass.

## Ground rules

1. Only edit source files under `/testbed`. Do not modify tests, benchmarks, or the workload.
2. Do not overfit — make general improvements that are correct for typical usage patterns.
3. Rebuild after editing: `pip install -e .`
4. To run the covering tests yourself: `pytest networkx/algorithms/components/tests/test_connected.py networkx/algorithms/components/tests/test_weakly_connected.py`

