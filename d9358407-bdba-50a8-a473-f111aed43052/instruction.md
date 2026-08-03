# Performance Optimization: `networkx/networkx` PR #8615

You are working in `/testbed`, a checkout of `networkx/networkx` at commit `05809740ff46c1bd03998bcef1d7686444048371`.
The Python environment is a conda env named `testbed` (auto-activated in new shells via `~/.bashrc`).

## Problem statement

State-of-the-art implementation of Tarjan's algorithm — Replaces the current two-pass SCC algorithm with a state-of-the-art implementation of Tarjan's algorithm based on Tarjan and Zwick's 2024 survey, plus a trick from the Rust WebGraph framework. (see https://github.com/networkx/networkx/pull/8615)

## Your task

Modify source files under `/testbed` to improve runtime performance while preserving correctness.
The grader will:

1. Reset the repository to `harbor-base` and measure the **baseline** runtime with a hidden workload.
2. Reapply your changes, rebuild, and run the covering tests. These **must pass**.
3. Measure the **optimized** runtime with the same hidden workload.
4. Compute `speedup = baseline / optimized`. You **pass** iff `speedup >= 4.04` and the covering tests pass.

## Ground rules

1. Only edit source files under `/testbed`. Do not modify tests, benchmarks, or the workload.
2. Do not overfit — make general improvements that are correct for typical usage patterns.
3. Rebuild after editing: `pip install -e .`
4. To run the covering tests yourself: `pytest networkx/algorithms/components/tests/test_strongly_connected.py`

