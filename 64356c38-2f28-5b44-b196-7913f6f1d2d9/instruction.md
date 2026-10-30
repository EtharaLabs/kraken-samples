# Faster program capture for long circuits

`/app/pennylane` is a checkout of PennyLane with its development environment
installed: `python` on the `PATH` imports the package from this tree, so your
edits take effect immediately. Work from `/app/pennylane`: from its parent `/app`, a bare
`import pennylane` resolves to the checkout directory instead of the package. With program capture enabled, building a jaxpr
of a long circuit takes far longer than it should, and the time grows faster
than the number of gates.

Reproduce it with the visible workload:

```
python /app/workload/trace_workload.py
```

It enables capture, traces a fixed, seeded list of 6,000 two- and three-qubit
controlled gates once with `jax.make_jaxpr`, and prints the tracing time and a
digest of the captured program.

## Goal

Make capture tracing of long circuits faster by changing the library source
under `/app/pennylane/pennylane/`. Done means:

- Tracing is substantially faster on long circuits. Speed is measured on hidden
  circuits that differ from the visible one, each traced once in a fresh process.
- Every captured program is identical to what the unmodified library produces:
  the same equations in the same order, so the printed digest does not change.
- The repository's existing tests keep passing, and existing functions keep
  accepting the arguments they accept today.
- The change reads like an ordinary library change: focused on the cause of
  the slowdown and written in the repository's own style. Reviewers read the
  diff as well as the timings.

The reward is continuous. It compares your speedup with a reference speedup on
the hidden circuits, and it is zero if any captured program differs, a covering
test fails, or a rule below is broken.

## Rules

- Edit only the library package `/app/pennylane/pennylane/`. Do not edit tests,
  the workload, benchmarks, or test and build configuration (`conftest.py`,
  `pyproject.toml`, `setup.py`, `uv.lock` and similar).
- Do not cache or persist results across runs or processes, for example by
  writing files or using shared memory, to make repeated runs look faster.
- Do not try to detect the evaluation: no inspecting the call stack, environment
  variables, command-line arguments, or the grading harness and its files.
- Do not special-case the visible workload's gate list, size, seed or digest.
- There is no network access. Do not reinstall or upgrade packages.
