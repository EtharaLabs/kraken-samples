<div align="center">

<img src="images/hero.png" alt="Kraken · repository-level performance optimization RL environment" style="width: 100%; height: auto;" />
</div>

> **Agentic-coding RL environment · Harbor-format tasks ·
> real GitHub PR–grounded workloads · binary reward in `{0, 1}` gated by
> correctness *and* measured speedup**

![scope](https://img.shields.io/badge/scope-repo--level_perf_optimization-blue)
![format](https://img.shields.io/badge/format-Harbor-FFD21F)
![reward](https://img.shields.io/badge/reward-tests_pass_∧_speedup_≥_target-brightgreen)
![status](https://img.shields.io/badge/status-pilot_sample_delivery-yellow)

Delivery of the **Kraken** RL training set: containerized
[Harbor-format](https://github.com/harbor-framework/harbor) tasks for
agentic performance engineering on **real repository code, at real
commits, against real workloads**.

This sample covers the **SWE-Perf–grounded scope**: tasks that
ask a coding agent to *optimize the runtime of a targeted workload*
inside a full checkout of a real repository at a pinned version,
without breaking the covering test suite the maintainers wrote
alongside the original expert patch. Each task is seeded from a
**merged source PR** that produced a measured speedup, which sets
the per-task **target speedup** the agent must match or exceed.

Kraken is the environment; **Kraken Samples** is the curated sample
delivery for evaluation, ablations, and dataset review. The parent RL
environment and its long-form methodology live in
[`Ethara-Ai/kraken`](https://github.com/Ethara-Ai/kraken); the
reference paper is
[SWE-fficiency (Ma et al., arXiv 2511.06090)](https://arxiv.org/abs/2511.06090).

## TL;DR

- **What it is.** A reinforcement-learning *environment sample* (not a
  static Q/A set): each task drops a coding agent into a container with a
  real project checkout, a targeted **workload script**, and a hidden
  covering test suite. The agent must produce a patch that (a) keeps
  the tests green and (b) makes the workload run at least as fast as the
  expert PR did. The scalar reward is the AND of those two conditions.
- **Why it discriminates.** The agent never sees the covering tests
  during authoring, and the workload script is executed verbatim against
  its patch — there is no way to game the grader without genuinely
  understanding the code path being optimized. A missing / empty patch
  scores exactly `0.0` via a size-guard in the verifier before any test
  runs.
- **Reproducibility posture.** Every task pins the source repository
  to a **base commit**, its language runtime to a **conda `testbed`
  env** at the exact version from the source PR, and its
  runtime container to a **3-tier Dockerfile** (base OS + build deps,
  conda env + shared pip deps, repo clone + install + `harbor-base` git
  tag). The `test_patch` from the source PR is applied at *eval time*,
  never baked into the image, so it can be revised independently of the
  environment layer.

## At a glance

| Field                | Value                                                                                                     |
| -------------------- | --------------------------------------------------------------------------------------------------------- |
| Domain               | Repository-level performance optimization (SWE-Perf–style)                                                |
| Format               | [Harbor](https://github.com/harbor-framework/harbor) containerized tasks                                  |
| Target speedup range | **1.02× → 26.92×** (median **1.61×**)                                                                     |
| Runtime versions     | pinned per task in `task.toml` (see task inventory)                                                       |
| Reward               | `1` iff (covering tests pass) ∧ (measured_speedup ≥ target_speedup); else `0`. Written to `/logs/verifier/reward.txt` |
| Task grounding       | One merged source GitHub PR per task (`metadata.pr_url` in `task.toml`)                                    |
| Namespace            | UUID `6f0f1a4c-3d3a-5f7e-9a2b-4d5c6e7f8a90` · task-org prefix `swe-perf/`                                  |
| Reference solution   | `solution/patch.diff` (the PR's expert patch)                                                             |
| Grading harness      | Harbor envelope + per-task `tests/test.sh` (workload timing + pytest correctness gate)                    |
| Status               | **Pilot sample delivery** — tasks migrated into Harbor envelope from the SWE-Perf–style scrape pipeline; native re-authoring through Trinity FORGE + `harbor build` is planned |

## Table of contents

- [TL;DR](#tldr)
- [At a glance](#at-a-glance)
- [Motivation & intended use](#motivation--intended-use)
- [What Kraken is](#what-kraken-is)
- [What's in this delivery](#whats-in-this-delivery)
  - [Task list](#task-list)
- [Repository layout](#repository-layout)
  - [The agent's contract, inside the container](#the-agents-contract-inside-the-container)
- [Methodology & reward design](#methodology--reward-design)
- [How grading works](#how-grading-works)
- [Quality posture](#quality-posture)
- [Status & roadmap](#status--roadmap)
- [`task.toml` quick reference](#tasktoml-quick-reference)
- [Reproducing a single task locally](#reproducing-a-single-task-locally)
- [Reproducibility & provenance](#reproducibility--provenance)
- [Versioning, licensing & citation](#versioning-licensing--citation)
- [Design notes](#design-notes)

---

### What ships in this delivery

| Deliverable                                       | Where it lives                                                                     |
| ------------------------------------------------- | ---------------------------------------------------------------------------------- |
| Task specification (the agent's brief)            | `dataset/<slug>/instruction.md`                                                    |
| Runtime image recipe (3-tier: OS · env · repo)    | `dataset/<slug>/environment/Dockerfile` + `setup_env.sh` + `setup_repo.sh`         |
| Deferred `test_patch` (applied at eval time)      | `dataset/<slug>/environment/test_patch.diff`                                       |
| Workload + verifier (`test.sh` entry point)       | `dataset/<slug>/tests/{test.sh, workload.py, measure.py}`                          |
| Harbor task metadata                              | `dataset/<slug>/task.toml`                                                         |
| Expert PR patch (validates the task admits `1.0`) | `dataset/<slug>/solution/patch.diff` + `solve.sh`                                  |
| UUID index + human-readable manifest              | `dataset/INDEX.md` + `dataset/manifest.json` + `dataset/by-uuid/<uuid> → ../<slug>` |

---

## Motivation & intended use

**Why this exists.** Static coding benchmarks emphasize *what* to
fix — pass a function, close a bug, satisfy a spec. Performance
engineering is the harder regime: the code already runs, the tests
already pass, and the agent must reason about *how* to make the same
program produce the same answer faster. As
[SWE-fficiency (arXiv 2511.06090)](https://arxiv.org/abs/2511.06090)
demonstrates, this is exactly where current agents underperform —
locating the bottleneck, reasoning across function boundaries, and
maintaining correctness under edits.

Kraken Samples targets that regime end-to-end: each task provides a
**complete real repository at a real commit**, a **workload that
  exercises the hot path** the source PR sped up, and a **held-out
covering test set** the PR shipped alongside the optimization. The
agent must beat the workload's baseline runtime *by the exact factor
the expert achieved*, without regressing any covering test.

**Primary intended use.** A *reinforcement-learning reward source* for
training and evaluating agentic code-generation models on real-world
performance engineering. The consumer runs their model on each task and
uses the binary reward as the training signal.

**Also suitable for.**

- **Offline evaluation** of an agent's ability to optimize unfamiliar
  codebases against a hidden test suite.
- **Ablations** on agent scaffolds, tool use, and reasoning budgets,
  holding the environment fixed.
- **Difficulty calibration** for downstream curriculum design — target
  speedups span two orders of magnitude across the corpus
  (**1.02× → 26.92×**), and the sampled tasks exercise substantively
  different code paths (HTTP client parsing, graph algorithms, template
  compilation, request routing, validator dispatch).

**Out of scope / not designed for.**

- **A leaderboard-grade benchmark as-is.** This is a *sample delivery* —
  it ships the tasks and grader for review and integration, not a
  ranking. Difficulty is **measured, never declared**: any per-task
  hardness label must be earned by signed pilots against a frozen solver
  registry, not asserted in the metadata.
- **Coverage of every SWE-Perf task.** The tasks in this sample are a
  subset of the broader Kraken corpus; the full dataset ships separately
  in [`Ethara-Ai/kraken-dataset`](https://github.com/Ethara-Ai/kraken-dataset).
- **Guaranteed uniform quality.** The tasks were emitted by the
  swefficiency-style scrape pipeline in `kraken-harness` and packaged
  into the Harbor envelope. Native re-authoring through Trinity FORGE +
  the Harbor CLI is roadmap; see [Status & roadmap](#status--roadmap).

**Audience.** ML researchers and engineers building or evaluating
agentic code models on real repository work, and authors extending
Kraken to new repositories or workload families.

---

## What Kraken is

Kraken produces training data for agentic code models on
**repository-level performance optimization**. Each task in the delivery
is a self-contained job in the Harbor format: a containerized workspace,
a spec, a hidden covering test suite plus a timed workload, and a
reference expert patch that validates the target speedup is attainable.
The consumer runs the tasks against their model and uses the resulting
reward as an RL signal.

The contract a model faces, per task, when the consumer runs it:

1. The model is dropped into a container with a fresh checkout of the
   repository at a pinned commit (`/testbed`), an activated
   conda env (`testbed`) at the exact runtime version the PR used, and
   an `instruction.md` that describes the workload it must speed up and
   points at the source PR for context.
2. The model edits the checked-out code. It does **not** see the
   covering test suite or the expert patch during authoring — only the
   workload script (`tests/workload.py`) it must accelerate.
3. `tests/test.sh` runs at grade time. It (a) snapshots the model's
   changes as a patch, (b) reruns the workload on the *unpatched*
   baseline to establish `BASELINE_MEAN`, (c) re-applies the model's
   patch on top of the pinned commit, (d) runs the covering tests
   (`pytest` under the shipped `test_patch`), and (e) reruns the
   workload on the *patched* code to establish `OPTIMIZED_MEAN`. The
   scalar reward is `1` iff the tests passed *and*
   `BASELINE_MEAN / OPTIMIZED_MEAN ≥ target_speedup`; otherwise `0`.

Because the agent never sees the covering tests during authoring, and
because the workload script is executed verbatim, the reward is graded
on the true observable behavior of the patched program, not on any
proxy the agent could pattern-match.

---

## What's in this delivery

| Top-level    | What it is                                                       |
| ------------ | ---------------------------------------------------------------- |
| `dataset/`   | Harbor-format tasks. One slug-named directory per task, mirrored under `dataset/by-uuid/<uuid>` for UUID lookups. |

Each task carries an `instance_id` (`<owner>__<repo>-<pr>`) and a
deterministic `uuid` derived from that ID under the namespace
`6f0f1a4c-3d3a-5f7e-9a2b-4d5c6e7f8a90`. Task-org prefix in `task.toml`
is `swe-perf/`.

### Task list

The authoritative task list is not embedded in this README. See:

- `dataset/manifest.json` — machine-readable manifest
- `dataset/INDEX.md` — human-readable slug ↔ uuid ↔ PR table

Speedup targets in this pilot span **1.02× → 26.92×** (median **1.61×**).

---

## Repository layout

```
kraken-samples/
├── README.md
├── LICENSE
└── dataset/
    ├── INDEX.md              # human-readable slug ↔ uuid ↔ PR table
    ├── manifest.json         # machine-readable manifest (namespace, task_org, tasks[])
    ├── by-uuid/
    │   └── <task-uuid>       # relative symlink → ../<slug>
    └── <slug>/               # one directory per task
        ├── task.toml         # Harbor task metadata (see below)
        ├── instruction.md    # the spec the agent sees
        ├── environment/
        │   ├── Dockerfile          # 3-tier: base OS + conda py311 + repo checkout
        │   ├── setup_env.sh        # tier 2: create testbed conda env @ row.python_version + pip deps
        │   ├── setup_repo.sh       # tier 3: clone source @ base_commit + install + git tag harbor-base
        │   └── test_patch.diff     # PR's covering-test patch; applied at EVAL time, not build time
        ├── tests/
        │   ├── test.sh             # Harbor verifier: snapshot → baseline → patch → tests → optimized → reward
        │   ├── workload.py         # the timed workload (agent may read this)
        │   └── measure.py          # extract Mean: from workload log, compute binary reward, write result.json
        └── solution/
            ├── patch.diff          # the PR's expert patch (validates that reward=1 is attainable)
            └── solve.sh            # oracle solver: reset → apply patch.diff → hand off to test.sh
```

### The agent's contract, inside the container

- **Workspace root.** `/testbed` — a fresh clone of the source
  repository at `metadata.base_commit`, tagged `harbor-base` for
  deterministic resets. The conda env `testbed` (at
  `metadata.python_version`) is auto-activated in new shells via
  `~/.bashrc`.
- **What the agent sees.**
  - The `instruction.md` at container startup, which points at the
    source PR and pastes the exact workload the grader will run.
  - The full checked-out source under `/testbed`.
  - The workload script at `/tests/workload.py` (identical to what the
    grader executes).
- **What the agent does not see.**
  - The covering test suite (arrives with the PR's `test_patch.diff`
    and is applied by the verifier *only* during grading).
  - The expert reference patch (`solution/patch.diff`).
  - The verifier logic (`tests/test.sh`, `tests/measure.py`) or its
    reward-write path.
- **How the agent submits.** By editing files under `/testbed`. There is
  no hand-off ceremony — the verifier snapshots whatever the working
  tree contains against `harbor-base` at grade time.
- **Reward sink.** `/logs/verifier/reward.txt` — a single line, `0` or
  `1`, written by `tests/test.sh` via `tests/measure.py`. A structured
  `result.json` lands alongside with `status`, `reward`, and
  `instance_id`.
- **Empty-patch guard.** If the agent's snapshotted patch is 0 bytes,
  `test.sh` writes `status=empty_patch`, `reward=0`, and exits before
  the covering tests run. A pass-through / no-op submission scores
  exactly `0.0` across the whole delivery.

---

## Methodology & reward design

### Reward construction

The reward is intentionally the simplest signal that is **jointly gated
on correctness and speed**:

```
reward = 1  iff  (all covering tests pass)  AND  (baseline_mean / optimized_mean  ≥  target_speedup)
reward = 0  otherwise
```

There is no partial credit, no gradient within a task, and no exit-code
shortcut — the scalar is computed only from (a) the pytest exit status
under the shipped `test_patch` and (b) the ratio of two `workload.py`
runs (`Mean:` lines extracted by `measure.py`, matched via
`r"Mean:\s*([0-9]+\.?[0-9]*(?:[eE][-+]?[0-9]+)?)"`).

**Why binary rather than smooth.** Performance optimization is
adversarial by construction: a "partly right" patch that (a) breaks a
test or (b) misses the speedup floor is not a partial win — it is a
regression the maintainer would revert. Binary reward makes the reward
match what the PR reviewer would say. Smooth reward variants (e.g. HSR
from the SWE-fficiency paper) are supported by the parent Kraken RL
environment; the sample delivery is deliberately conservative here and
grades on the strict AND. See [Status & roadmap](#status--roadmap).

**Why per-PR target speedup rather than an absolute floor.** Every task
inherits its `target_speedup` from a **merged source PR that already
achieved that speedup**. This anchors difficulty in real engineering
work, not an authored threshold, and means the "reward = 1" ceiling is
provably attainable — the expert patch under `solution/patch.diff`
reaches it by construction.

### Discrimination

Each task is constructed to separate strong from weak policies:

- **Floor.** All tasks in this delivery have an effective empty-submission floor of
  `0.0`, enforced by the size-guard on the snapshotted patch inside
  `tests/test.sh` (writes `status=empty_patch`, `reward=0`).
- **Ceiling.** The expert PR patch (`solution/patch.diff`) passes the
  covering tests and produces at least the target speedup on the same
  container, so `reward = 1` is attainable in principle. Oracle
  reproducibility is validated by `solution/solve.sh`, which resets to
  `harbor-base`, applies the reference patch, and hands off to
  `test.sh`.
- **Spread.** Between these bounds the AND of (tests-pass) and
  (speedup ≥ target) gates the reward on both correctness reasoning
  and profiling / hot-path localization. A patch that reaches the
  speedup but subtly breaks an edge-case test scores `0`; a patch that
  passes every test but only halves the target speedup also scores `0`.

### Anti-gaming design

- The covering tests are **withheld from the agent** and injected only
  at grade time via `test_patch.diff`. The agent cannot fit-to-tests.
- The workload script is **executed verbatim** — no proxy metric, no
  self-report. The grader times an actual invocation of
  `workload.py`.
- The **baseline is re-timed on the same container** as the optimized
  run, back-to-back with no other work interleaved, so the speedup
  ratio is not confounded by host-level noise between different image
  builds.
- The size-guard rejects **no-op / whitespace-only** submissions at 0
  bytes before pytest is even invoked — a pass-through submission
  cannot accidentally score `1` on a trivially cached workload.

---

## How grading works

`tests/test.sh` is the single E2E entrypoint per task. It writes reward
to `/logs/verifier/reward.txt` and per-run detail to
`/logs/verifier/result.json`. The full flow, in order:

1. **Snapshot.** `git add -A && git diff --cached harbor-base >
   /logs/verifier/agent_patch.diff`. If the patch is 0 bytes, write
   `status=empty_patch`, `reward=0`, and exit `0`.
2. **Baseline.** `git reset --hard harbor-base && git clean -fdx …`,
   apply `test_patch.diff` (with a whitespace-ignoring fallback),
   reinstall the package (`pip install -e .` + shared runtime deps),
   run `python /tests/workload.py > /logs/verifier/baseline.out`,
   extract `BASELINE_MEAN` via `measure.py --extract`.
3. **Optimized.** Reset to `harbor-base` again, apply the snapshotted
   agent patch (with the same whitespace-ignoring fallback; failure
   writes `status=agent_patch_failed`, `reward=0`, exit `0`), apply
   `test_patch.diff` on top (failure writes
   `status=test_patch_failed_optimized`), reinstall.
4. **Correctness gate.** Run `pytest`, capturing to
   `/logs/verifier/test_output.txt`. `TEST_STATUS = ${PIPESTATUS[0]}`.
5. **Optimized timing.** Run the workload again, extract
   `OPTIMIZED_MEAN`.
6. **Grade.** `measure.py` computes
   `measured_speedup = BASELINE_MEAN / OPTIMIZED_MEAN` and writes
   `reward = 1` iff `TEST_STATUS == 0` **and**
   `measured_speedup ≥ target_speedup`, else `reward = 0`. Numeric
   detail (`baseline_mean`, `optimized_mean`, `measured_speedup`,
   `target_speedup`, `test_status`) lands in
   `/logs/verifier/result.json`.
7. **Always exit `0`.** The reward file is the grading channel, not the
   shell exit code.

The `test_patch` layering — copied into the image at
`/opt/harbor/test_patch.diff` but applied by `test.sh` at eval time,
never baked into git — is deliberate: covering-test patches from real
PRs are whitespace-fragile, and applying them at eval time lets the
tests be revised (or re-scraped) without invalidating the container
build cache.

---

## Quality posture

Every task in this delivery satisfies, or is designed to satisfy:

- **Discriminative reward.** The expert PR patch under
  `solution/patch.diff` is the intended `reward = 1` witness; an empty
  submission scores `reward = 0` via the size-guard before pytest runs.
  Both bounds are enforced by the grader itself, not by convention.
- **Real-world grounding.** Every task is seeded from a *merged*
  source PR that produced a measured speedup. `metadata.pr_url` links
  the source PR; `metadata.base_commit` pins the pre-optimization
  commit; `metadata.target_speedup` is the number the maintainer's
  patch achieved.
- **Hermetic execution.** The container is Ubuntu 22.04 + Miniconda
  py3.11 at the base layer, with the task's conda `testbed` env pinned
  to `metadata.python_version` and per-task pip pins. `PYTHONUNBUFFERED=1`,
  `LC_ALL=C.UTF-8`, and `LANG=C.UTF-8` are baked in; no network is
  required at grade time once the image is built.
- **Deterministic resets.** Every reset is `git reset --hard
  harbor-base && git clean -fdx -e .venv -e "*.egg-info"`, so the
  baseline and optimized runs start from byte-identical trees plus
  whatever the two patches apply.
- **Test-patch isolation.** The PR's covering test patch lives at
  `environment/test_patch.diff` and is applied *only* by the verifier,
  never at build time. Corrupt or whitespace-fragile test patches
  cannot brick the image; the verifier handles them with a
  whitespace-tolerant `git apply --ignore-space-change` fallback and,
  on hard failure, writes a distinct `status=test_patch_failed_*` for
  triage.
- **Oracle self-check.** `solution/solve.sh` is a self-contained
  oracle: it resets to `harbor-base`, applies `patch.diff`, and hands
  control to `tests/test.sh`. It is the intended acceptance test the
  task author (and the auditor) runs to confirm the target speedup is
  attainable on the shipped image.

**Not yet enforced by tooling** (see [Status & roadmap](#status--roadmap)):

- **Signed pilot difficulty.** No per-task tier label is asserted in
  this delivery; difficulty must be measured by external signed pilots
  against a frozen solver registry before it is claimed. The
  `target_speedup` column is not a difficulty proxy.
- **Uniform test-patch quality.** Because the covering-test patches were
  extracted from real PRs, their granularity varies (some ship 3 focused
  regression tests, some ship a broader refactor of the test file). The
  Trinity FORGE migration is the mechanism by which per-task test
  discrimination will be re-authored to a uniform bar.

---

## Status & roadmap

This is a **pilot sample delivery**. State the sharp edges plainly:

- **Origin.** The tasks were emitted by the SWE-Perf–style scrape
  pipeline in
  [`Ethara-Ai/kraken-harness`](https://github.com/Ethara-Ai/kraken-harness)
  (`generate_harbor_tasks.py`), which reads SWE-Perf JSONL rows
  (per-repo JSONL splits, one file per sampled repository)
  and materializes each row into the Harbor task layout you see under
  `dataset/`. The Harbor *envelope* (`task.toml`, `instruction.md`,
  `environment/`, `tests/`, `solution/`) is native; the *authoring
  path* is not yet the Harbor CLI.
- **Reward.** The verifier grades on the **binary AND** of
  (covering tests pass) and (measured_speedup ≥ target_speedup). The
  parent Kraken RL environment additionally supports the smooth
  **Harmonic Speedup Ratio (HSR)** described in
  [SWE-fficiency (arXiv 2511.06090)](https://arxiv.org/abs/2511.06090);
  a smooth-reward variant of this sample is on the roadmap, gated on
  the same correctness precondition.
- **Task quality is heterogeneous.** Because tasks are derived from
  real PRs of varying scope, the covering-test granularity, workload
  representativeness, and optimization surface differ from task to
  task. This delivery does **not** claim per-task uniform difficulty.
- **Difficulty is not yet measured.** No pilot rewards are reported in
  this delivery. A calibration pass across a candidate model and a
  weaker calibration model — following the raiden-samples pattern of
  a pass@1 sweep with `reward.txt` per run — is planned before the
  first labeled release.
- **Migration path.** The delivery target is the same task set (or a curated
  successor set) re-emitted through:
  1. **[Trinity FORGE](https://github.com/Ethara-Ai/trinity)** for
     content-addressed authoring with a difficulty ledger, matching the
     methodology used by the sibling `rinzler-samples` delivery.
  2. **[Harbor `harbor build`](https://github.com/harbor-framework/harbor)**
     for native, content-addressed emission of the Harbor task bundle
     (self-computed UUID over `(config, seed, instruction, checkers)`).
  3. The
     [`Ethara-Ai/kraken`](https://github.com/Ethara-Ai/kraken)
     harness surface (`kraken` CLI) for pipeline orchestration and
     smooth-reward variants aligned with the SWE-fficiency paper.
  Local development of the Harbor authoring path lives under
  `/Users/macbookpro/harbor` on the pilot machine; the migration
  target repo is `Ethara-Ai/harbor` once vendored.

Nothing in the layout below is expected to change through the
migration; the *authoring path* is what moves.

---

## `task.toml` quick reference

Each task carries a small TOML metadata file used by the Harbor runner
and by downstream tooling. The actual shape, with one concrete task as
the example (repo- and PR-identifying fields shown as placeholders):

```toml
version = "1.0"

[task]
name = "swe-perf/<instance_id>"

[metadata]
instance_id     = "<owner>__<repo>-<pr>"
uuid            = "67a43895-30eb-51da-8d8e-c0cf72918ff1"
repo            = "<owner>/<repo>"
base_commit     = "90967ccb9ab1f757c2637a68ea2e16b8da2605f4"
pr_url          = "https://github.com/<owner>/<repo>/pull/<pr>"
pull_number     = 5229
target_speedup  = 1.130362
python_version  = "3.8"

difficulty = "hard"                        # advisory, not yet pilot-verified
category   = "performance_optimization"
tags       = ["optimization", "sweperf"]

[verifier]
timeout_sec = 3600

[agent]
timeout_sec = 10800

[environment]
build_timeout_sec = 3600
cpus              = 4
gpus              = 0
memory_mb         = 8192
storage_mb        = 20000
```

Fields with load-bearing semantics:

- `[metadata].instance_id` — SWE-Perf-style `<owner>__<repo>-<pr>` slug,
  and the directory name under `dataset/`.
- `[metadata].uuid` — deterministic UUIDv5 under the namespace
  `6f0f1a4c-3d3a-5f7e-9a2b-4d5c6e7f8a90`, so `dataset/by-uuid/<uuid>`
  resolves via symlink to the slug directory.
- `[metadata].base_commit` — the source commit the container clones
  and tags `harbor-base`.
- `[metadata].target_speedup` — the number the verifier compares
  `baseline_mean / optimized_mean` against.
- `[metadata].python_version` — the exact runtime the conda
  `testbed` env is created at.
- `[metadata].difficulty` — **advisory only** in this delivery; not yet
  backed by signed pilots.
- `[environment]` — resource / timeout envelope the runner enforces.

---

## Reproducing a single task locally

The tasks are self-contained Harbor bundles. To reproduce the oracle
(reference) run for one task locally:

```bash
TASK=dataset/<slug>    # pick any slug listed in dataset/INDEX.md

# 1. Build the task image from the per-task Dockerfile.
docker build -t kraken-samples:$(basename "$TASK") "$TASK/environment/"

# 2. Run the oracle path — apply the reference patch, run the verifier,
#    print the reward.
docker run --rm \
  -v "$PWD/$TASK/tests:/tests:ro" \
  -v "$PWD/$TASK/solution:/solution:ro" \
  -v "$PWD/logs-$(basename "$TASK"):/logs" \
  kraken-samples:$(basename "$TASK") \
  bash -lc "
    bash /solution/solve.sh &&
    bash /tests/test.sh &&
    cat /logs/verifier/reward.txt
  "
```

Expected outcome on a correctly built image: `reward.txt` contains
`1`, and `result.json` shows `status=success` with a `measured_speedup`
at or above the task's `target_speedup`.

To grade an *agent's* submission instead of the oracle, replace the
`solve.sh` invocation with the agent's patch application (or the
harness's snapshot step) before invoking `tests/test.sh`.

---

## Reproducibility & provenance

**What is fully reproducible.** *Grading* is deterministic and offline
by construction once the image is built: pytest runs under the shipped
`test_patch`, the workload is executed by the same interpreter under
the same conda env, and the reward is a pure function of
`(TEST_STATUS, BASELINE_MEAN, OPTIMIZED_MEAN, target_speedup)`. Given
the same submission and the same image, the *pass/fail* verdict is
reproducible; the *speedup ratio* has ordinary host-level timing noise
and is compared with a `≥` gate so small jitter does not flip the
verdict near the target.

**What is build-time reproducible.** The image is built in three tiers
by design:

- **Tier 1** — `ubuntu:22.04` + apt bundle (`gfortran`, `libopenblas-dev`,
  `libblas-dev`, `liblapack-dev`, `libffi-dev`, `libssl-dev`,
  `libtiff-dev`, `zlib1g-dev`, tzdata, locales) + Miniconda py3.11.
  Byte-identical across every task in the delivery, so the Docker layer
  cache reuses it after the first build.
- **Tier 2** — `setup_env.sh` creates conda env `testbed` at
  `metadata.python_version`, then installs shared pip deps
  (`pytest`, plus any per-repo overrides).
- **Tier 3** — `setup_repo.sh` clones the source repo at
  `metadata.base_commit`, runs the per-repo install command, pip-freezes
  the state, and `git tag harbor-base` for reset invariance. The PR's
  `test_patch.diff` is `COPY`d into the image at
  `/opt/harbor/test_patch.diff` but **not applied** at build time —
  application is deferred to the verifier.

**Pins that are not yet at parity with the raiden-samples posture.** This
delivery does **not** yet pin the base image or task images by `sha256`
digest, does not yet ship a `task_checksum` per task, and does not yet
have a published ECR mirror for the pre-built images. Digest pinning and
checksum emission are part of the Harbor CLI migration described in
[Status & roadmap](#status--roadmap).

**Provenance today.** Each task's identity is fixed by
`(instance_id, uuid, base_commit)` in `task.toml`; grading harness
identity is the shipped `tests/test.sh` at whatever commit of this
repository the consumer cloned.

---

## Versioning, licensing & citation

**Versioning.** This is the **Kraken Samples pilot delivery** — tasks
derived from merged source PRs across the sampled repositories.
Task identity is the tuple `(slug, uuid, base_commit)` in `task.toml`;
the in-repository task identity is the git commit of this repository
you cloned. There is no semantic version tag on the delivery itself.
When reporting results, cite the git commit + the per-task
`instance_id` + `base_commit`.

**Licensing.** This delivery ships under the license at `LICENSE` at the
repository root. Source repository code that the container clones
at grade time retains its respective license and is *not*
redistributed by this
repository — it is fetched at image build time via `setup_repo.sh`.

**Citation.** When reporting results computed against this delivery,
identify (a) the task set (`Kraken Samples pilot`),
(b) the exact task content (`instance_id` + `base_commit` per task),
(c) the grading harness (this repository's `tests/test.sh` at the
cited commit), and (d) the model and scaffold you ran against them.
The reference paper for the underlying task family is:

```bibtex
@misc{ma2025swefficiency,
  title        = {SWE-fficiency: Can Language Models Optimize Real-World Repositories on Real Workloads?},
  author       = {Ma, Jeffrey Jian and Hashemi, Milad and Yazdanbakhsh, Amir and Swersky, Kevin and Press, Ofir and Li, Enhui and Reddi, Vijay Janapa and Ranganathan, Parthasarathy},
  year         = {2025},
  eprint       = {2511.06090},
  archivePrefix= {arXiv},
  primaryClass = {cs.SE},
  url          = {https://arxiv.org/abs/2511.06090}
}
```

The parent Kraken RL environment:

```bibtex
@misc{kraken2026,
  title        = {Kraken: An RL Environment for Repository-Level Performance Optimization},
  author       = {Ethara.AI},
  year         = {2026},
  howpublished = {\url{https://github.com/Ethara-Ai/kraken}},
  note         = {Harbor-format tasks; agent optimizes real repository workloads under a hidden covering test suite.}
}
```

---

## Design notes

1. **Why real PRs, not synthetic workloads.** Every task is anchored in
   a *merged* source PR that measurably sped something up. The
   `target_speedup` is therefore a number a human maintainer already
   hit, on real code, that a real reviewer accepted — not an authored
   threshold. This is the anti-gaming property that matters most: the
   ceiling is provably reachable, and by an edit the community
   endorsed.
2. **Why deferred `test_patch` application.** Covering-test patches
   from real PRs are whitespace-fragile and occasionally reference
   fixtures that get renamed later. Baking them into the image at build
   time would couple test-suite maintenance to environment cache
   invalidation. The verifier applies the patch at eval time with an
   `--ignore-space-change` fallback and, on hard failure, writes a
   diagnostic `status=test_patch_failed_*` so the failure mode is
   triage-visible instead of silent.
3. **Why `git tag harbor-base`.** Every reset — baseline pass and
   optimized pass — resets to the same tag, so the two runs start from
   byte-identical trees. Combined with `git clean -fdx` (preserving
   `.venv` and `*.egg-info` to avoid reinstalls), this makes the ratio
   `BASELINE_MEAN / OPTIMIZED_MEAN` a clean function of the agent's
   patch and nothing else.
4. **Why binary reward here, HSR in the parent env.** A sample delivery is a
   review artifact; a binary AND on (tests-pass, speedup-hits-target)
   is the strictest possible reward and the cheapest to audit. The
   parent Kraken environment exposes the smooth HSR variant described
   in the SWE-fficiency paper for training. The two are compatible: the
   binary reward is the indicator function of HSR being at ceiling on
   the correctness dimension and at or above target on the speedup
   dimension.
5. **Why hybrid slug + UUID indexing.** Slugs (`<owner>__<repo>-<pr>`)
   are the natural human-facing identifier and the SWE-Perf convention;
   UUIDs (`67a43895-30eb-51da-8d8e-c0cf72918ff1`) are the natural
   machine-facing identifier and the Harbor convention. The `by-uuid/`
   symlink tree gives auditors expecting UUID paths a stable lookup
   without duplicating task content.
6. **Scaling to more environments.** The per-task footprint
   (`instruction.md` + `environment/{Dockerfile, setup_env.sh,
   setup_repo.sh, test_patch.diff}` + `tests/{test.sh, workload.py,
   measure.py}` + `solution/{patch.diff, solve.sh}` + `task.toml`) is
   uniform across all tasks, generated from a single parametrized
   scrape recipe. The same layout generalizes to any SWE-Perf–style
   JSONL row for any target repository — the Trinity FORGE + `harbor
   build` migration replaces the *authoring* step, not the *envelope*.

---

**Kraken Samples** · An Ethara.AI project · Environment:
[Kraken](https://github.com/Ethara-Ai/kraken) · Task format:
[Harbor](https://github.com/harbor-framework/harbor) · Reference paper:
[SWE-fficiency (arXiv 2511.06090)](https://arxiv.org/abs/2511.06090).
