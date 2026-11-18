<p align="center"><img src="images/hero.svg" alt="Kraken" width="720"></p>

# Kraken: samples

<p align="center"><b>The samples lane: 5 of 30 Harbor task bundles.</b></p>

<p align="center"><a href="#summary"><img src="https://img.shields.io/badge/bundles-5_of_30-845EF7" alt="bundles: 5 of 30"></a> <a href="#evidence-status"><img src="https://img.shields.io/badge/sealed-4-845EF7" alt="sealed: 4"></a> <a href="#difficulty-tiers"><img src="https://img.shields.io/badge/difficulty-measured-845EF7" alt="difficulty: measured"></a></p>

<p align="center"><sub><a href="#abstract">Abstract</a> | <a href="#summary">Summary</a> | <a href="#difficulty-tiers">Difficulty tiers</a> | <a href="#evidence-status">Evidence status</a> | <a href="#coverage">Coverage</a> | <a href="#dataset-structure">Dataset structure</a> | <a href="#verification-and-quality-assurance">Verification and quality assurance</a> | <a href="#reproduction">Reproduction</a> | <a href="#cite">Cite</a> | <a href="#license">License</a> | <a href="#contact">Contact</a></sub></p>

## Abstract

The curated lane of this corpus: at most 30 Harbor task bundles, every anchor seated first and every other bundle in seal order. Bundles past that ceiling live in `delivery/`.

Each bundle is one Harbor task in a directory named by its content-derived uuid5, so the name doubles as an integrity check. This page is rendered from the resident bundles on every reconcile; a value a bundle does not carry reads `absent`, and the page never fills one in.

## Summary

| Property | Value |
| --- | --- |
| Bundles | 5 of 30 |
| Sealed | 4 of 5 |
| Registrations | sample (4), unregistered (1) |
| Audit verdicts | none (5) |
| Harbor schema | 1.4 (5) |

## Difficulty tiers

Difficulty is measured by the signed pilot alone and never declared in a bundle, so this page states no tier a bundle claims.

## Evidence status

The verdict is the audit outcome recorded at the sealed digest, and `none` means no verdict has landed for that digest yet. Only an authoring run removes a bundle from this lane, so removal waits for the next one.

| uuid | Verdict | Sealed digest | Stream |
| --- | --- | --- | --- |
| 402717e5-0ada-5914-bc78-01e7b1d9337b | none | absent | none |
| 87ec7a10-cfc2-5ea6-aa61-a922bf9db6b0 | none | `64f7a29408c4ecf4827afbdeeb56174d2f8eed8985ebd64b04de2272c732df8f` | forge-ankit-ethara-ethara-ai-20261030t023322z-cc5b51 |
| 496c6249-46bd-5b5d-9723-0730665e7c51 | none | `7d97c8015673f72f11f280ba1e01467a28b69957a0af92526d80395d19801d28` | forge-ankit-ethara-ethara-ai-20261103t131824z-eaae43 |
| 015a6071-67df-5d6f-8e11-e538be4b1e0b | none | `2cb02d2de4a94c8569e82ec7f4dd3ebe3121475242ea268734becb32e6e79d72` | forge-yasiraliint17-wq-20261110t140106z-1f3c37 |
| e27499cd-a843-5dec-9974-9fac21853371 | none | `58cd12f4b9b4cf00a0a086fb9c1acaab8c458f0609717540996916e92f11abb9` | forge-ankitethara-odoo-20261110t180802z-a4be3b |

## Coverage

| Keyword | Bundles |
| --- | --- |
| continuous-reward | 5 |
| performance-optimization | 5 |
| python | 5 |
| long-horizon | 2 |
| c | 1 |
| cirq | 1 |
| coordinate-descent | 1 |
| credit-assignment | 1 |
| cython | 1 |
| elastic-net | 1 |
| isin | 1 |
| jax | 1 |
| lasso | 1 |
| measurement-noise-control | 1 |
| numpy | 1 |
| pennylane | 1 |
| program-capture | 1 |
| quantum-circuits | 1 |
| scikit-learn | 1 |
| statsmodels | 1 |
| stringdtype | 1 |
| transformers | 1 |
| zivot-andrews | 1 |

## Dataset structure

| Bundle | Task | Keywords | Registration | Sealed at | Tier |
| --- | --- | --- | --- | --- | --- |
| [`402717e5-0ada-5914-bc78-01e7b1d9337b`](402717e5-0ada-5914-bc78-01e7b1d9337b/) | `ethara/402717e5-0ada-5914-bc78-01e7b1d9337b` | continuous-reward, measurement-noise-control, performance-optimization, python, statsmodels, zivot-andrews | unregistered | unsealed | - |
| [`87ec7a10-cfc2-5ea6-aa61-a922bf9db6b0`](87ec7a10-cfc2-5ea6-aa61-a922bf9db6b0/) | `ethara/87ec7a10-cfc2-5ea6-aa61-a922bf9db6b0` | continuous-reward, credit-assignment, jax, pennylane, performance-optimization, program-capture, python | sample | 2026-10-30T06:29:57Z | - |
| [`496c6249-46bd-5b5d-9723-0730665e7c51`](496c6249-46bd-5b5d-9723-0730665e7c51/) | `ethara/496c6249-46bd-5b5d-9723-0730665e7c51` | c, continuous-reward, isin, numpy, performance-optimization, python, stringdtype | sample | 2026-11-06T18:26:53Z | - |
| [`015a6071-67df-5d6f-8e11-e538be4b1e0b`](015a6071-67df-5d6f-8e11-e538be4b1e0b/) | `ethara/015a6071-67df-5d6f-8e11-e538be4b1e0b` | cirq, continuous-reward, long-horizon, performance-optimization, python, quantum-circuits, transformers | sample | 2026-11-10T22:02:34Z | - |
| [`e27499cd-a843-5dec-9974-9fac21853371`](e27499cd-a843-5dec-9974-9fac21853371/) | `ethara/e27499cd-a843-5dec-9974-9fac21853371` | continuous-reward, coordinate-descent, cython, elastic-net, lasso, long-horizon, performance-optimization, python, scikit-learn | sample | 2026-11-11T15:57:27Z | - |

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#131a33","primaryTextColor":"#e8ecff","primaryBorderColor":"#845EF7","lineColor":"#22d3ee","fontFamily":"monospace"}}}%%
flowchart LR
    bundle["&lt;uuid&gt;/"]
    bundle --> n0["task.toml<br/>runner manifest"]
    bundle --> n1["instruction.md<br/>objective the agent reads"]
    bundle --> n2["environment/<br/>agent sandbox image"]
    bundle --> n3["tests/<br/>verifier, hidden from the agent"]
    bundle --> n4["solution/<br/>private oracle"]
    bundle --> n5["LICENSE-NOTICE.md"]
    bundle --> n6["README.md"]
    bundle --> n7["trials/"]
```

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#131a33","primaryTextColor":"#e8ecff","primaryBorderColor":"#845EF7","lineColor":"#22d3ee","fontFamily":"monospace"}}}%%
flowchart LR
    staging["staging/"]
    staging --> samples["samples/<br/>5 of 30"]
    samples --> delivery["delivery/<br/>0 of 10000"]
    delivery --> stock["stock/<br/>0 of 10000"]
```

## Verification and quality assurance

Each bundle's signed provenance carrier holds its screening roots, screening instant, and absolute expiry. Placement moves that carrier into the private derivation set, which this page never reads, so reconcile lists no root it cannot verify here.

## Reproduction

Each bundle directory is a complete Harbor task: `task.toml` is the runner manifest, `instruction.md` the objective, `environment/` the sandbox image, and `tests/` the verifier. Point a Harbor runner at one bundle directory to reproduce it; `solution/` stays private.

## Cite

```bibtex
@misc{kraken2026,
  title  = {Kraken: Repository-Level Performance Optimization Tasks},
  author = {{Ethara.AI}},
  year   = {2026},
  note   = {Grounded in SWE-fficiency (Ma et al., arXiv:2511.06090).}
}
```

## License

Kraken is released under the MIT License, Copyright (c) 2026 Ethara.AI. The full text lives at [LICENSE](LICENSE).

## Contact

- Organization: Ethara.AI at <https://github.com/Ethara-Ai>
- Security disclosures: `security@ethara.ai`; the report classes, response targets, and safe-harbor terms are stated once in [SECURITY.md](SECURITY.md).
- Contribution route: entry rules and the where-changes-go routing are stated in [CONTRIBUTING.md](CONTRIBUTING.md); ownership by path is declared in [.github/CODEOWNERS](.github/CODEOWNERS).

Copyright (c) 2026 Green Rider Technology LLP (Ethara AI). All rights reserved.
