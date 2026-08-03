# Performance Optimization: `pallets/jinja` PR #1516

You are working in `/testbed`, a checkout of `pallets/jinja` at commit `99b6fc7f37449f009b5c114b8159ccd4d10c1167`.
The Python environment is a conda env named `testbed` (auto-activated in new shells via `~/.bashrc`).

## Problem statement

Async template rendering has unnecessary overhead from auto_await wrapping every coroutine call. Adding a fast-path check with inspect.isawaitable() before wrapping reduces async overhead significantly.

## Hints

The auto_await utility always wraps return values. Short-circuiting for non-awaitable values eliminates wrapper overhead.

## Your task

Modify source files under `/testbed` to improve runtime performance while preserving correctness.
The grader will:

1. Reset the repository to `harbor-base` and measure the **baseline** runtime with a hidden workload.
2. Reapply your changes, rebuild, and run the covering tests. These **must pass**.
3. Measure the **optimized** runtime with the same hidden workload.
4. Compute `speedup = baseline / optimized`. You **pass** iff `speedup >= 1.25` and the covering tests pass.

## Ground rules

1. Only edit source files under `/testbed`. Do not modify tests, benchmarks, or the workload.
2. Do not overfit — make general improvements that are correct for typical usage patterns.
3. Rebuild after editing: `pip install -e .`
4. To run the covering tests yourself: `pytest tests/test_nativetypes.py`

