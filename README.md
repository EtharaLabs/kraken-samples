<p align="center"><img src="images/hero.svg" alt="Kraken" width="720"></p>

# Kraken SWE-efficiency: Samples

<p align="center"><b>Five sample tasks from Kraken, a Harbor benchmark built on SWE-fficiency (arXiv:2511.06090) of performance work on real scientific Python libraries.</b></p>

<p align="center"><sub><a href="#abstract">Abstract</a> | <a href="#summary">Summary</a> | <a href="#tasks">Tasks</a> | <a href="#trials">Trials</a> | <a href="#dataset-structure">Dataset structure</a> | <a href="#reproduction">Reproduction</a> | <a href="#cite">Cite</a> | <a href="#contact">Contact</a></sub></p>

## Abstract

Kraken is a benchmark of software-efficiency tasks built on the [SWE-fficiency](https://arxiv.org/abs/2511.06090) benchmark (Ma et al., arXiv:2511.06090), in [Harbor](https://www.harborframework.com/) format. Each task takes a real open-source scientific library at a pinned commit, points the agent at a slow code path through a visible workload script, and asks for a much faster implementation that returns the same results as the unmodified library.

Every task runs the agent in a container with no network and carries a reference solution and a verifier that runs in a separate container. The verifier rebuilds the submitted library, checks that every result matches the unmodified library, runs the repository's own tests, and times the submission against the base and reference implementations on seed-randomized inputs. The reward is continuous between 0 and 1.

This repository holds the five-task sample. The tasks cover quantum circuit compilation (Cirq and PennyLane), time-series statistics (statsmodels), array operations (numpy) and sparse regression (scikit-learn).

## Summary

| Property | Value |
| --- | --- |
| Tasks | 5 |
| Libraries | Cirq, statsmodels, numpy, PennyLane, scikit-learn |
| Format | Harbor task |
| Platforms | linux/amd64, linux/arm64 |
| Reward | bounded continuous, 0 to 1 |
| Agent | Claude Code with `claude-opus-5-5` (Claude Opus 5.5) |

## Tasks

| Task | Library | Upstream change | Objective |
| --- | --- | --- | --- |
| [`015a6071`](015a6071-67df-5d6f-8e11-e538be4b1e0b/) | Cirq | quantumlib/Cirq #8197 | Speed up Cirq's single-qubit merge transformers on long circuits while returning the same circuits. |
| [`402717e5`](402717e5-0ada-5914-bc78-01e7b1d9337b/) | statsmodels | statsmodels/statsmodels #10602 | Speed up the Zivot-Andrews unit-root test on long series while keeping its results and error behaviour. |
| [`496c6249`](496c6249-46bd-5b5d-9723-0730665e7c51/) | numpy | numpy/numpy #32693 | Speed up `np.isin` on `StringDType` arrays while returning the same results. |
| [`87ec7a10`](87ec7a10-cfc2-5ea6-aa61-a922bf9db6b0/) | PennyLane | PennyLaneAI/pennylane #10298 | Make jaxpr capture of large PennyLane programs scale with circuit size while emitting the same program. |
| [`e27499cd`](e27499cd-a843-5dec-9974-9fac21853371/) | scikit-learn | scikit-learn/scikit-learn #34572 | Speed up the coordinate descent regularization paths and cross-validated estimators while returning the same fits. |

## Trials

Each task was run with Claude Code driving Claude Opus 5.5 and scored by the task's own verifier. Trials are stored in each task's `trials/opus-5.5/`.

| Task | Model | Agent | Reward | Cost (USD) | Agent time |
| --- | --- | --- | --- | --- | --- |
| [015a6071-67df-5d6f-8e11-e538be4b1e0b](015a6071-67df-5d6f-8e11-e538be4b1e0b/trials/opus-5.5/) | claude-opus-5-5 | claude-code 2.1.325 | 0.3874 | 2.38 | 16m 31s |
| [402717e5-0ada-5914-bc78-01e7b1d9337b](402717e5-0ada-5914-bc78-01e7b1d9337b/trials/opus-5.5/) | claude-opus-5-5 | claude-code 2.1.326 | 0.6471 | 2.12 | 14m 54s |
| [496c6249-46bd-5b5d-9723-0730665e7c51](496c6249-46bd-5b5d-9723-0730665e7c51/trials/opus-5.5/) | claude-opus-5-5 | claude-code 2.1.325 | 0.4090 | 1.10 | 7m 5s |
| [87ec7a10-cfc2-5ea6-aa61-a922bf9db6b0](87ec7a10-cfc2-5ea6-aa61-a922bf9db6b0/trials/opus-5.5/) | claude-opus-5-5 | claude-code 2.1.325 | 0.5758 | 0.53 | 41m 45s |
| [e27499cd-a843-5dec-9974-9fac21853371](e27499cd-a843-5dec-9974-9fac21853371/trials/opus-5.5/) | claude-opus-5-5 | claude-code 2.1.326 | 0.5294 | 4.93 | 31m 2s |

Each trial folder is Harbor's trial output:

| Path | Contents |
| --- | --- |
| `config.json`, `lock.json` | Trial configuration and resolved run settings, including the task digest |
| `result.json` | Agent, model, token usage, cost, timings, and verifier reward |
| `agent/` | Agent trajectory (`trajectory.json`), Claude Code transcript (`claude-code.txt`), and session files |
| `verifier/` | `reward.json`, `reward.txt`, measurement records, and test output |
| `artifacts/` | Files collected from the paths declared in `task.toml`: the agent's working tree of the library |

## Dataset structure

Each task is one Harbor task in a directory named by its uuid.

```
<uuid>/
├── task.toml         runner manifest
├── instruction.md    objective the agent reads
├── environment/      sandbox image: the library at the pinned commit and the visible workload
├── tests/            verifier, hidden from the agent
├── solution/         reference solution
└── trials/
    └── opus-5.5/     run with Claude Opus 5.5
```

## Reproduction

Each task directory is a complete Harbor task: `task.toml` is the runner manifest, `instruction.md` the objective, `environment/` the sandbox image, `tests/` the verifier, and `solution/` the reference solution. The trials above were produced with:

```bash
harbor run -a claude-code -m anthropic/claude-opus-5-5
```

## Cite

```bibtex
@misc{kraken2026,
  title        = {Kraken: Repository-Level Performance Optimization Tasks},
  author       = {{Ethara.AI}},
  year         = {2026},
  note         = {Grounded in SWE-fficiency (Ma et al., arXiv:2511.06090).}
}
```

## Contact

Kraken SWE-efficiency is built by [Ethara.AI](https://github.com/Ethara-Ai). For questions about the benchmark or dataset, contact [research@ethara.ai](mailto:research@ethara.ai).

Copyright (c) 2026 Green Rider Technology LLP (Ethara AI). All rights reserved.
