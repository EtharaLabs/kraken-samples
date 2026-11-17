# Golden trajectory, ethara/2e800ea2-45d0-5685-a47c-f39d9bb6a4ab

The ordered path a solver walks through `instruction.md`. Each step names the action, the state it establishes, and the checker identifier it satisfies. Every deliverable and every red line of the bound contract appears as a step, and every step binds one.

## Deliverable

- **D1**, the modified Cirq working tree at `/app/cirq`. Harbor snapshots it out of the agent container and re-materializes it at the same path in the separate verifier, where the graded tree is rebuilt from the pristine base tree plus the submission's edits to the library source alone.

## Ordered path

1. **Read the statement and see the problem.** `instruction.md` points at `python /app/workload/merge_workload.py`, which builds one gauge-transformed trotter-like circuit, times both PhasedXZ transformers on it and prints a digest of each result's structure. Reading the transformers shows the time is spent on work that grows with the length of each run of single-qubit operations or moments, not on a single gate conversion.

   - establishes: the length of a run, not one conversion, is the target
   - satisfies: none yet; this is the discovery step the archetype measures

2. **Make the merge path do less work per run.** The change belongs in the single-qubit merge path itself: how the unitary of a small circuit operation is computed, the transformers of `cirq-core/cirq/transformers/merge_single_qubit_gates.py`, and the moment-merging primitives they call. A run of single-qubit operations or moments is folded in one pass rather than by repeated pairwise work over its length.

   - establishes: the cost of a merge no longer grows the way the base tree's does
   - satisfies: F1, F2, F3 and `d1_outcome_work_not_deferred`

3. **Keep every result identical to the base tree's.** For every timed case of every family the submission's output equals the base tree's output: the same moment count; per moment the same operations on the same qubits with the same tags and the same non-unitary operations, each operation's unitary equal up to a global phase within 1e-7; the same nesting and repetitions of circuit operations; the product of each moment's global phase operations equal within 1e-7; and cirq.unitary results equal within 1e-7, phase included.

   - establishes: the gate check G-EQUIV holds on every case of every family
   - satisfies: the gate, and with it every graded item

4. **Combine the global phases of one merged run.** When `cirq.merge_single_qubit_moments_to_phxz` merges several moments that each carry a global phase operation, the merged moment carries a single `cirq.GlobalPhaseGate` whose coefficient is the product of those phases, and one phase operation alone stays as it is. The equivalence check reads the product of each moment's global phase operations within 1e-7, so a dropped or doubled phase is a mismatch.

   - establishes: the merged phase convention of the statement holds
   - satisfies: G-EQUIV on the F2 cases that carry global phases

5. **Keep one-qubit circuit operations unitary-correct.** `cirq.unitary` of a one-qubit `cirq.CircuitOperation` returns the matrix of its circuit raised to its repetitions, negative repetitions included, and still raises `TypeError` when the circuit has no unitary, for example because it contains a measurement.

   - establishes: the F3 unitary cases return the base matrices, phase included
   - satisfies: G-EQUIV on the F3 unitary cases, and `F3`

6. **Keep the repository's own tests passing.** The repository's own tests under cirq-core/cirq/transformers, cirq-core/cirq/circuits and cirq-core/cirq/protocols/unitary_protocol_test.py are collected and pass against the graded tree, with the three covering test files restored from the overlay so a submission cannot pass by weakening the tests it is judged against. No public function loses a call signature it supports now.

   - establishes: the library still behaves as its own suite requires
   - satisfies: the gate check G-TESTS

7. **Earn the speed on unseen circuits, in fresh processes.** Every timing runs in a fresh process, rotated across base, reference and submission, so no side warms a cache for another. Each family draws one grading-time seed, rejected while it equals the visible workload seed, so the timed circuits are never the ones the visible script builds. The statistic is T is the median of the repeated timings of the case; the case score is clamp(ln(T_base / T_sub) / ln(T_base / T_ref), 0, 1), and the family score is the median of its informative case scores.

   - establishes: the measured gain is a property of the code, not of the harness or of the visible script
   - satisfies: F1, F2, F3, and the red lines RL2 and RL4

8. **Stay inside the editable surface and tell nothing about the grader.** /app/cirq/cirq-core/cirq/ library source only. *_test.py, conftest.py, cirq/testing/ and JSON test data are protected, and so are benchmarks/, dev_tools/, check/, pyproject.toml, setup.py, setup.cfg, every requirements file, tox.ini and pytest.ini. No state survives between runs or processes, and no added line reads the call stack, the process environment, the command line, the user or home directory, or the grader's files.

   - establishes: the gate check G-RL holds, so no red line is recorded
   - satisfies: the red lines RL1, RL2 and RL3

9. **Leave a diff an upstream reviewer would accept.** The diff stays inside the single-qubit merge path with no unrelated rewrite, reformatting or dead code; every docstring and comment it adds or changes describes what the new code does; the speed comes from doing less work inside the call rather than from a lazy result read later; and no module-level, class-level or function-attribute state keeps a unitary, a decomposition or a merged result from one call for a later one.

   - establishes: the judged share of the reward is earned
   - satisfies: d1_craft_diff_scope, d1_craft_comments_match, rl2_process_global_cache, rl4_robustness_visible_special_case, d1_outcome_work_not_deferred

## Red lines, each as its own step

- **RL1.** Only library source under /app/cirq/cirq-core/cirq/ may change, and no protected path, and no harness file may change while the submission runs Established by: treeops builds the graded tree from the base tree and the submission; a changed path matching the protected pattern is recorded as an edited protected path, and measure.py re-hashes every pinned harness file after the run and records a change.
- **RL2.** No state survives between runs or processes to flatter repeated timings, whether through files, shared memory, a resident process or anything similar Established by: a line-level scan of the added lines for persistence constructs, plus a persistence guard that reports files left outside the run scratch by any child.
- **RL3.** Code must not try to tell when it is being graded, for example by reading the call stack, the process environment, the command line, the user or home directory, or the grader's files Established by: a line-level scan of the added lines for stack, environment, argv, uid and grader-path constructs.
- **RL4.** Nothing may be tailored to the visible workload script's particular circuit, qubits, sizes or seed Established by: a line-level scan of the added lines for the visible workload literals of tests/harness/config.json, and every timed case draws a fresh grading-time seed that is never the visible one.

## Checker identifiers this path satisfies

- `F1` (F1, obligation D1, dimension outcome, compiled, weight 5): On cirq.merge_single_qubit_gates_to_phxz over gauge-transformed trotter-like circuits of different grids, layer counts, exponents and cycle counts, drawn at grading time, the submission's median time per case clears the base median by more than the family's measured noise band, and the family score is the median over its discriminating cases of clamp(ln(T_base / T_sub) / ln(T_base / T_ref), 0, 1).
- `F2` (F2, obligation D1, dimension outcome, compiled, weight 5): On cirq.merge_single_qubit_moments_to_phxz over deep circuits whose runs of consecutive single-qubit moments have many different lengths, from 2 up to about two dozen, separated by two-qubit or measurement moments and some carrying global phase operations, plus trotter-like circuits, the submission's median time per case clears the base median by more than the family's measured noise band, and the family score is the median over its discriminating cases of clamp(ln(T_base / T_sub) / ln(T_base / T_ref), 0, 1).
- `F3` (F3, obligation D1, dimension coverage, compiled, weight 3): The speedup reaches the rest of the single-qubit merge path and not only the two headline transformers: cirq.merge_single_qubit_gates_to_phased_x_and_z on random circuits, cirq.unitary of one-qubit CircuitOperations with repetitions, nested circuit operations and tags, and both PhasedXZ transformers under cirq.TransformerContext(deep=True, tags_to_ignore=...) all clear the family's measured noise band, and the family score is the median over its discriminating cases of clamp(ln(T_base / T_sub) / ln(T_base / T_ref), 0, 1).
- `d1_craft_diff_scope` (d1_craft_diff_scope, obligation D1, dimension craft, judged, weight 1): The diff is confined to Cirq's single-qubit merge path: the unitary computation of small circuit operations, the single-qubit merge transformers in merge_single_qubit_gates.py, the moment-merging primitives they call, and any export of a helper they add. It carries no unrelated rewrites, reformatting or dead code (unused helpers, unreachable branches, commented-out code).
- `d1_craft_comments_match` (d1_craft_comments_match, obligation D1, dimension craft, judged, weight 1): Every docstring and comment the diff adds or changes describes what the new code actually does (for example which moments are merged at once, how repetitions are applied, how global phases are combined), and no existing docstring is left describing behaviour the code no longer has.
- `rl2_process_global_cache` (rl2_process_global_cache, obligation RL2, dimension process, judged, weight 1, prohibition): The diff adds module-level, class-level or function-attribute state (for example a dict, lru_cache or functools.cache over gates, operations, circuits or matrices) that keeps computed unitaries, decompositions or merged results from one transformer call for reuse by a later call.
- `rl4_robustness_visible_special_case` (rl4_robustness_visible_special_case, obligation RL4, dimension robustness, judged, weight 1, prohibition): The diff special-cases the visible workload rather than speeding up the general path: it branches on its qubit layout, gate exponent, cycle count, circuit size, the CZ gauge transformer's output shape, or a threshold tuned to that script.
- `d1_outcome_work_not_deferred` (d1_outcome_work_not_deferred, obligation D1, dimension outcome, judged, weight 1): The speedup comes from doing less work inside the transformer or unitary call, not from moving the work out of it: the diff does not return lazy circuits, moments or operations whose matrices or decompositions are computed only when the result is later read.

- the gate: The gate is open only when the measurement record has status ok, no red line RL1 to RL4 fired, and the covering tests were collected with no failure. A closed gate writes reward exactly 0.0. Inside an open gate each family score S_f is itself 0 when any case of that family is not equivalent to the base output or the submission's run for that family failed.
- the gate check `G-EQUIV` (obligation D1, carrier `tests/harness/equiv.py`): For every timed case of every family the submission's output equals the base tree's output: the same moment count; per moment the same operations on the same qubits with the same tags and the same non-unitary operations, each operation's unitary equal up to a global phase within 1e-7; the same nesting and repetitions of circuit operations; the product of each moment's global phase operations equal within 1e-7; and cirq.unitary results equal within 1e-7, phase included.
- the gate check `G-TESTS` (obligation D1, carrier `tests/harness/repotests.py`): The repository's own tests under cirq-core/cirq/transformers, cirq-core/cirq/circuits and cirq-core/cirq/protocols/unitary_protocol_test.py are collected and pass against the graded tree, with the three covering test files restored from the overlay so a submission cannot pass by weakening the tests it is judged against.
- the gate check `G-RL` (obligation RL1, carrier `tests/harness/treeops.py`): No red line RL1 to RL4 is recorded in the measurement record.

## The three timed families

- **F1** (weight 0.25, 6 hidden cases), `cirq.merge_single_qubit_gates_to_phxz`: gauge-transformed trotter-like circuits of different grids, layer counts, exponents and cycle counts.
- **F2** (weight 0.4, 6 hidden cases), `cirq.merge_single_qubit_moments_to_phxz`: deep circuits whose runs of consecutive single-qubit moments have many different lengths, from 2 up to about two dozen, separated by two-qubit or measurement moments, some carrying global phase operations, plus trotter-like circuits.
- **F3** (weight 0.2, 8 hidden cases), `cirq.merge_single_qubit_gates_to_phased_x_and_z, cirq.unitary, both PhasedXZ transformers deep`: random circuits through merge_single_qubit_gates_to_phased_x_and_z; cirq.unitary of one-qubit CircuitOperations with repetitions, including negative ones, nested circuit operations and tags; and both PhasedXZ transformers under cirq.TransformerContext(deep=True, tags_to_ignore=...) on circuits that wrap runs of single-qubit gates in circuit operations, some tagged to be ignored.

The noise band is per family, the largest ln spread of the base tree's own repeated timings, clamped to the closed interval from 0.05 to 0.15. A speedup over base at or below the band scores 0, and a submission within the band of the reference scores 1. A case whose reference gain ln(T_base / T_ref) is at or below twice the band cannot discriminate and is dropped from the family median; a family with no discriminating case is a measurement error, never a score.

## Rejected routes

- **public_fix_only** (K3): Reward about 0.3 compiled: the upstream pull request alone does not reach the reference speed, so memorisation of the public fix does not saturate the reward
- **lazy_result** (K4): The gate opens and the timing improves, but d1_outcome_work_not_deferred fails and the judged share is lost; a lazy result that changes the walked output also fails G-EQUIV and zeroes the family
- **global_cache** (K5): Reward 0 or near it: the persistence guard and the line scan record RL2, which closes the gate
- **visible_special_case** (K6): Reward 0 on the literal route (RL4 recorded) and no speedup on the hidden route, because the grading-time seed is never the visible one
- **protected_edit** (K7): Reward 0: an edit to a test file, conftest.py, cirq/testing/ or a build setting is discarded by the graded-tree build and recorded as RL1, which closes the gate

## Why the ordering is forced

The gate stands before every graded item, so a faster merge that changes one moment, one tag or one global phase earns nothing and the equivalence step cannot be deferred. With no judge configured: reward = (0.25 S_F1 + 0.40 S_F2 + 0.20 S_F3) / 0.85. With a judge configured: reward = 0.25 S_F1 + 0.40 S_F2 + 0.20 S_F3 + 0.15 J. A red line or a failed covering test sets the reward to 0. No term multiplies J by any speed score. The judged items are never multiplied by a family speed term, so a defensible diff that is not faster earns the judged share alone and a fast diff that an upstream reviewer would reject loses it; and an empty diff is never sent to the judge. The reference is a faster original implementation rather than the public upstream fix, so reproducing the public fix lands partway up the ladder instead of at the top.

Revision note (2026-11-16): re-sent with the revision 2 task files unchanged so that the image build runs again.
