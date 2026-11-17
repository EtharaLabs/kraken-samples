# Speed up Cirq's single-qubit merge transformers

## Background

A development checkout of Cirq lives at `/app/cirq`. The `python` interpreter on
your `PATH` imports `cirq` straight from `/app/cirq/cirq-core`, so a saved source
edit is picked up on the next run. The tree has its own test suite; run it with
`python -m pytest` from `/app/cirq`.

Cirq's transformers that fold runs of single-qubit gates into `PhasedXZGate`s are
slow on long circuits. On a trotter-like circuit put through the CZ gauge
transformer, `cirq.merge_single_qubit_gates_to_phxz` and
`cirq.merge_single_qubit_moments_to_phxz` spend most of their time on work that
grows with the length of each run of single-qubit operations or moments.

## Seeing the problem

```
python /app/workload/merge_workload.py
```

The script builds one such circuit, times both transformers on it, and prints a
digest of each result's structure.

## What to deliver

Change Cirq's library source so that single-qubit merging is much faster. The
work is done when all of these hold:

1. **Much faster on every kind of circuit below,** not only the script's circuit,
   at any size and seed, already on the first call in a new Python process. All
   three groups matter:
   - `cirq.merge_single_qubit_gates_to_phxz` on gauge-transformed trotter-like
     circuits of different grids, layer counts, exponents and cycle counts;
   - `cirq.merge_single_qubit_moments_to_phxz` on deep circuits whose runs of
     consecutive single-qubit moments have many different lengths (from 2 up to
     about two dozen), separated by two-qubit or measurement moments, some
     carrying global phase operations, plus trotter-like circuits;
   - `cirq.merge_single_qubit_gates_to_phased_x_and_z` on random circuits;
     `cirq.unitary` of one-qubit `cirq.CircuitOperation`s (with repetitions,
     including negative ones, nested circuit operations and tags); and both
     PhasedXZ transformers with `cirq.TransformerContext(deep=True,
     tags_to_ignore=...)` on circuits that wrap runs of single-qubit gates in
     circuit operations, some tagged to be ignored.
2. **Same results as now.** For every input above, the output must match what the
   unmodified library returns: the same number of moments; in each moment, the
   same operations on the same qubits with the same tags, each operation's
   unitary equal to the original's up to a global phase within `1e-7`, the same
   non-unitary operations, the same nesting and repetitions of circuit
   operations; and the product of each moment's global phase operations equal to
   the original product within `1e-7`. `cirq.unitary` results must equal the
   original matrices within `1e-7`, phase included.
3. **Global phases of one merged run may be combined.** When
   `cirq.merge_single_qubit_moments_to_phxz` merges several moments that each
   carry a global phase operation, the merged moment must carry a single
   `cirq.GlobalPhaseGate` whose coefficient is the product of those phases
   (one phase operation alone stays as it is).
4. **One-qubit circuit operations keep their unitary behaviour.**
   `cirq.unitary` of a one-qubit `cirq.CircuitOperation` returns the matrix of
   its circuit raised to its repetitions (for example `X` repeated twice is the
   identity), and still raises `TypeError` ("cirq.unitary failed ...") when the
   circuit has no unitary, for example because it contains a measurement.
5. **The existing tests still pass**, under `/app/cirq/cirq-core/cirq/transformers`,
   `/app/cirq/cirq-core/cirq/circuits` and
   `/app/cirq/cirq-core/cirq/protocols/unitary_protocol_test.py`, and no public
   function loses a call signature it supports now.
6. **The patch reads like normal upstream work.** In particular:
   - keep the diff to the single-qubit merge path (how the unitary of a small
     circuit operation is computed, the transformers in
     `/app/cirq/cirq-core/cirq/transformers/merge_single_qubit_gates.py`, the moment-merging
     primitives they call, and exports of any helper you add), with no unrelated
     rewrites, reformatting or dead code;
   - make every docstring and comment you add or change describe what the new
     code actually does, and leave no existing docstring describing behaviour the
     code no longer has;
   - get the speed by doing less work inside the call, not by returning lazy
     objects that do the work when the result is read later;
   - add no module-level, class-level or function-attribute caches that keep
     unitaries, decompositions or merged results from one call for a later one.

## Constraints

- Only library source under `/app/cirq/cirq-core/cirq/` may change, and not its
  test modules (every module whose name ends in `_test`),
  `/app/cirq/cirq-core/cirq/conftest.py`,
  `/app/cirq/cirq-core/cirq/testing/` or JSON test data. Leave the workload script
  `/app/workload/merge_workload.py`, `/app/cirq/benchmarks/`, `/app/cirq/dev_tools/`,
  `/app/cirq/conftest.py`, and the build and test settings
  (`/app/cirq/pyproject.toml`, `/app/cirq/setup.py`, `/app/cirq/cirq-core/setup.py`,
  `/app/cirq/cirq-core/requirements.txt`) alone.
- No state may survive between calls, runs or processes to speed up later calls,
  whether through files, shared memory, a resident process or anything similar.
- Library behaviour must depend only on the inputs of each call: do not change it
  based on the call stack, environment variables, command-line arguments, the user
  or home directory, or files outside the library.
- Nothing may be tailored to the script's particular circuit, qubits, sizes or seed.
- The sandbox is offline. Do not install, reinstall or upgrade packages.
