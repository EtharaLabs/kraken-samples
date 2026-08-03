# Performance Optimization: `networkx/networkx` PR #8296

You are working in `/testbed`, a checkout of `networkx/networkx` at commit `6dbed05b693d535f70495229c3adc364793b00ed`.
The Python environment is a conda env named `testbed` (auto-activated in new shells via `~/.bashrc`).

## Problem statement

Kruskal MST early break for efficiency — Adds an early-exit guard to the Kruskal loop in the MST routines so the algorithm stops as soon as the spanning tree is complete. (see https://github.com/networkx/networkx/pull/8296)

## Your task

Modify source files under `/testbed` to improve runtime performance while preserving correctness.
The grader will:

1. Reset the repository to `harbor-base` and measure the **baseline** runtime with a hidden workload.
2. Reapply your changes, rebuild, and run the covering tests. These **must pass**.
3. Measure the **optimized** runtime with the same hidden workload.
4. Compute `speedup = baseline / optimized`. You **pass** iff `speedup >= 1.2` and the covering tests pass.

## Ground rules

1. Only edit source files under `/testbed`. Do not modify tests, benchmarks, or the workload.
2. Do not overfit — make general improvements that are correct for typical usage patterns.
3. Rebuild after editing: `pip install -e .`
4. To run the covering tests yourself: `pytest networkx/algorithms/tree/tests/test_mst.py`

