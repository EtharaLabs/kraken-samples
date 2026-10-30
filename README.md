<p align="center"><img src="images/hero.svg" alt="Kraken" width="720"></p>

# Kraken: samples

<p align="center"><b>The samples lane: 1 of 30 Harbor task bundles.</b></p>

<p align="center"><a href="#summary"><img src="https://img.shields.io/badge/bundles-1_of_30-845EF7" alt="bundles: 1 of 30"></a> <a href="#evidence-status"><img src="https://img.shields.io/badge/sealed-1-845EF7" alt="sealed: 1"></a> <a href="#difficulty-tiers"><img src="https://img.shields.io/badge/difficulty-measured-845EF7" alt="difficulty: measured"></a></p>

<p align="center"><sub><a href="#abstract">Abstract</a> | <a href="#summary">Summary</a> | <a href="#difficulty-tiers">Difficulty tiers</a> | <a href="#evidence-status">Evidence status</a> | <a href="#coverage">Coverage</a> | <a href="#dataset-structure">Dataset structure</a> | <a href="#verification-and-quality-assurance">Verification and quality assurance</a> | <a href="#reproduction">Reproduction</a> | <a href="#cite">Cite</a> | <a href="#license">License</a> | <a href="#contact">Contact</a></sub></p>

## Abstract

The curated lane of this corpus: at most 30 Harbor task bundles, every anchor seated first and every other bundle in seal order. Bundles past that ceiling live in `delivery/`.

Each bundle is one Harbor task in a directory named by its content-derived uuid5, so the name doubles as an integrity check. This page is rendered from the resident bundles on every reconcile; a value a bundle does not carry reads `absent`, and the page never fills one in.

## Summary

| Property | Value |
| --- | --- |
| Bundles | 1 of 30 |
| Sealed | 1 of 1 |
| Registrations | unregistered (1) |
| Audit verdicts | none (1) |
| Harbor schema | 1.4 (1) |

## Difficulty tiers

Difficulty is measured by the signed pilot alone and never declared in a bundle, so this page states no tier a bundle claims.

## Evidence status

The verdict is the audit outcome recorded at the sealed digest, and `none` means no verdict has landed for that digest yet. Only an authoring run removes a bundle from this lane, so removal waits for the next one.

| uuid | Verdict | Sealed digest | Stream |
| --- | --- | --- | --- |
| 64356c38-2f28-5b44-b196-7913f6f1d2d9 | none | `734da286388cf601e8b4d783e9cee4a2d1e12ef31fdab0e60dd816d5a511a6e3` | forge-ankit-ethara-ethara-ai-20261026t134628z-b5ea82 |

## Coverage

| Keyword | Bundles |
| --- | --- |
| continuous-reward | 1 |
| credit-assignment | 1 |
| jax | 1 |
| pennylane | 1 |
| performance-optimization | 1 |
| program-capture | 1 |
| python | 1 |

## Dataset structure

| Bundle | Task | Keywords | Registration | Sealed at | Tier |
| --- | --- | --- | --- | --- | --- |
| [`64356c38-2f28-5b44-b196-7913f6f1d2d9`](64356c38-2f28-5b44-b196-7913f6f1d2d9/) | `ethara/pennylane-capture-wrapped-operator-tracing` | continuous-reward, credit-assignment, jax, pennylane, performance-optimization, program-capture, python | unregistered | 2026-10-28T15:50:09Z | - |

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#131a33","primaryTextColor":"#e8ecff","primaryBorderColor":"#845EF7","lineColor":"#22d3ee","fontFamily":"monospace"}}}%%
flowchart LR
    bundle["&lt;uuid&gt;/"]
    bundle --> n0["task.toml<br/>runner manifest"]
    bundle --> n1["instruction.md<br/>objective the agent reads"]
    bundle --> n2["environment/<br/>agent sandbox image"]
    bundle --> n3["tests/<br/>verifier, hidden from the agent"]
    bundle --> n4["solution/<br/>private oracle"]
```

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#131a33","primaryTextColor":"#e8ecff","primaryBorderColor":"#845EF7","lineColor":"#22d3ee","fontFamily":"monospace"}}}%%
flowchart LR
    staging["staging/"]
    staging --> samples["samples/<br/>1 of 30"]
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
