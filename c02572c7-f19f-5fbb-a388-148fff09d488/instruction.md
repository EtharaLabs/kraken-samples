# Performance Optimization: `networkx/networkx` PR #6337

You are working in `/testbed`, a checkout of `networkx/networkx` at commit `1515862e8ed0aa9f1894f28b780ba19e81e9454b`.
The Python environment is a conda env named `testbed` (auto-activated in new shells via `~/.bashrc`).

## Problem statement

The _single_shortest_path helper in unweighted.py iterates inefficiently when building BFS layers. The current implementation rebuilds the next level dict from scratch each iteration. Optimization: use dict update instead of iterating and checking membership for each neighbor.

## Your task

Modify source files under `/testbed` to improve runtime performance while preserving correctness.
The grader will:

1. Reset the repository to `harbor-base` and measure the **baseline** runtime with a hidden workload.
2. Reapply your changes, rebuild, and run the covering tests. These **must pass**.
3. Measure the **optimized** runtime with the same hidden workload.
4. Compute `speedup = baseline / optimized`. You **pass** iff `speedup >= 2.08` and the covering tests pass.

## Ground rules

1. Only edit source files under `/testbed`. Do not modify tests, benchmarks, or the workload.
2. Do not overfit — make general improvements that are correct for typical usage patterns.
3. Rebuild after editing: `pip install -e .`
4. To run the covering tests yourself: `pytest networkx/algorithms/shortest_paths/tests/test_unweighted.py`

