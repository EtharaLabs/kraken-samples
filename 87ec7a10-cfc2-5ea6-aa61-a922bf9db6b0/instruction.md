# Speed up jaxpr capture of large PennyLane programs

## Background

A development checkout of PennyLane lives at `/app/pennylane`, and the `python`
interpreter on your `PATH` loads the library directly from that tree, so a saved
source edit is picked up on the next run. Run commands from inside
`/app/pennylane`; launched from `/app` instead, `import pennylane` would find the
checkout folder rather than the installed package.

When PennyLane's program capture is switched on, turning a big circuit into a
jaxpr is slow, and doubling the gate count more than doubles the time.

## Seeing the problem

```
python /app/workload/trace_workload.py
```

This script turns capture on, calls `jax.make_jaxpr` once over a seeded list of
6,000 controlled operations acting on two or three wires, then reports how long
tracing took along with a digest of the resulting program.

## What to deliver

Change library code under `/app/pennylane/pennylane/` so that capture scales
well on large circuits. Your work is accepted when all of these hold:

1. Large circuits trace much faster, not only the one in the script, each on a
   single trace in a new Python process.
2. Capture output is unchanged: for every circuit, the program has exactly the
   equations the original code emits, in the original order, and so the same
   digest.
3. The existing test suite still passes, and no public function loses a call
   signature it supports now.
4. The patch looks like normal upstream work: it targets the root cause of the
   slowdown and follows the conventions already used in the codebase. In
   particular:
   - keep the diff to the operator-removal code: `pop_op_eqns` in
     `/app/pennylane/pennylane/core/operator/operator2.py`, `remove_from_program`
     in `/app/pennylane/pennylane/core/queuing.py`, and the code that calls them,
     with no unrelated rewrites, reformatting or dead code;
   - make the `pop_op_eqns` docstring and any comment you add describe what the
     new code actually does (which equations are removed, in what order, and
     when the search stops), and keep `pylint: disable` comments scoped as they
     are now.

## Constraints

- Only files inside `/app/pennylane/pennylane/` may change. Leave tests under
  `/app/pennylane/tests/`, the workload script `/app/workload/trace_workload.py`,
  benchmarks, and the build and test settings in `/app/pennylane` alone (for
  instance `/app/pennylane/conftest.py`, `/app/pennylane/pyproject.toml`,
  `/app/pennylane/setup.py`, `/app/pennylane/uv.lock`).
- No state may survive between runs or processes to flatter repeated timings,
  whether through files, shared memory or anything similar.
- Code must not change its behaviour based on the call stack, environment
  variables, command-line arguments, or files outside the library.
- Nothing may be tailored to the script's particular gate list, gate count,
  seed or digest.
- The sandbox is offline. Do not install, reinstall or upgrade packages.
