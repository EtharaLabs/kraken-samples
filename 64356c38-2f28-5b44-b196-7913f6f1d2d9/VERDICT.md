# VERDICT

CRUCIBLE LOW report for run `crucible-ankit-ethara-ethara-ai-20261028t163000z-eb3df7`, audit of sealed bundle `64356c38-2f28-5b44-b196-7913f6f1d2d9` (PennyLane program-capture tracing, seal `734da286388c`) and its one author-side Opus 5.5 rollouts, 2026-10-29.

## Executive summary


- ✅ Oracle 1.0 in all three runs with every judged item passing, nop 0.0, four of five adversary probes 0.0, agent image clean of solution and verifier artifacts including /tmp, verifier in a separate container, statement and verifier aligned.
- Gate summary: 44 instrument records, 34 pass, 7 finding, 3 coverage gap; the bundle outcome is retained for FORGE rework under a new uuid.

## Disposition

🟡 HOLD:PILOT_REQUIRED

## Findings

### Grader discrimination (class 19)

- 🟡 G-ALT-SOLUTION, retained: suffix-sweep scored 1.0, reverse-search 0.9848 and tail-peek 0.9697; d1_outcome_cause_removed names pop_op_eqns as the place the fix must live, and both alternates' docstrings misdescribe their removal.
- 🟢 G-MUTANT-LADDER, retained: measured rungs 0.0, 0.2386, 0.3039, 0.4154, 0.5455 and 1.0 for the full fix; S1 is described as fixing the CNOT family but fails the expert lookup-count test, and S5 is described as earning a qp.prod share it does not earn.

### Statement and grader integrity (class 18)

- 🟡 G-ADV, retained: wrong program 0.0, cross-process caching 0.0 (RL2, RL3), evaluation detection 0.0 (RL3), test edit 0.0 (RL1), special-casing 6000 0.9848 with no red line.
- ✅ G-STMT-RECONCILE and G-STMT-LITERAL, acknowledged clean: every graded check maps to a statement line and every statement rule to a check or to the no-network policy; the speed thresholds are hidden by design, as in the reference benchmark.

### Domain integrity and reward provenance (class 6)

- 🟡 G-REWARD-PROVENANCE, retained: four gradings of pilot trial M9TEYcq gave 0.5606, 0.5455, 0.5606 and 0.5606 with compiled 0.4909 each time.
- ✅ G-ROLLOUT-INTEGRITY, G-ROLLOUT-ISOLATION and G-ROLLOUT-BYTES, acknowledged clean: four rollouts on the sealed bytes, rewards recompute from their own records, no trajectory touches verifier or solution paths.

### Supply-chain defects (class 5)

- 🟡 G-ENV-SBOM, retained: about 7 Critical and 130 High findings per image from the Debian base and the repository's locked dependencies; filelock 3.32.7 is verifier-only, never imported by the harness, behind a no-network verifier.

### Agent-evaluator isolation and environment build (class 20)

- ✅ G-CON-STRIP, G-ISO-COPY, G-ISO-IMPORT, G-ISO-HISTORY, G-ISO-FRESH, G-ENV-BUILD, G-ENV-ARCH, G-ENV-REGISTRY and G-ENV-LINT, acknowledged clean: /tmp and /var/tmp empty, no .git, no solution or verifier files, runner uid cannot write the harness, two clean builds per image differ only in build metadata, both pinned bases pull without credentials.

## Coverage gaps

- Every CRUCIBLE_VIEW screening root is null, so exclusion, freeze and near-duplicate screening resolve against no named list.
- No judge-reliability declaration under principle 5a; one judged item flipped across gradings of one diff.
- No signed external pilot over the frozen bytes; the Opus 5.5 rollout are author-side probes, pass@1 to pass@4 = 0.
- The verifier image's linux/amd64 build fails under the Mac's Colima emulation; the same bytes built under emulation on EC2 on 2026-10-28.
- The grype database was five weeks old at scan time, so vulnerability counts are a lower bound.

## Escalations

- FORGE rework under a new uuid superseding the audited bundle: reword d1_outcome_cause_removed, fix both alternate docstrings, add 6000 to the RL4 literals on token boundaries, judge median of three samples, correct the S1 and S5 rung effects, and add the task.toml specification and rationale blocks; instruction.md and environment/ stay byte-identical, so no rollout rerun is needed.
- A counted pilot needs either a signed external pilot or a self-pilot run through harness/ after its judge passthrough and harness configuration are fixed.

## Flag legend

- 🔴 retained finding that caps the bundle outcome; 🟡 retained finding to fix or accept; 🟢 low-severity retained finding; ✅ acknowledged clean.
