<p align="center"><img src="images/hero.svg" alt="Project" width="720"></p>

# Project: samples

<p align="center"><b>The samples lane: 5 of 30 Harbor task bundles.</b></p>

<p align="center"><a href="#summary"><img src="https://img.shields.io/badge/bundles-5_of_30-845EF7" alt="bundles: 5 of 30"></a> <a href="#evidence-status"><img src="https://img.shields.io/badge/sealed-0-845EF7" alt="sealed: 0"></a> <a href="#difficulty-tiers"><img src="https://img.shields.io/badge/difficulty-measured-845EF7" alt="difficulty: measured"></a></p>

<p align="center"><sub><a href="#abstract">Abstract</a> | <a href="#summary">Summary</a> | <a href="#difficulty-tiers">Difficulty tiers</a> | <a href="#evidence-status">Evidence status</a> | <a href="#coverage">Coverage</a> | <a href="#dataset-structure">Dataset structure</a> | <a href="#verification-and-quality-assurance">Verification and quality assurance</a> | <a href="#reproduction">Reproduction</a> | <a href="#cite">Cite</a> | <a href="#license">License</a> | <a href="#contact">Contact</a></sub></p>

## Abstract

The curated lane of this corpus: at most 30 Harbor task bundles, every anchor seated first and every other bundle in seal order. Bundles past that ceiling live in `delivery/`.

Each bundle is one Harbor task in a directory named by its content-derived uuid5, so the name doubles as an integrity check. This page is rendered from the resident bundles on every reconcile; a value a bundle does not carry reads `absent`, and the page never fills one in.

## Summary

| Property | Value |
| --- | --- |
| Bundles | 5 of 30 |
| Sealed | 0 of 5 |
| Registrations | unregistered (5) |
| Audit verdicts | none (5) |
| Harbor schema | absent (5) |

## Difficulty tiers

Difficulty is measured by the signed pilot alone and never declared in a bundle, so this page states no tier a bundle claims.

## Evidence status

The verdict is the audit outcome recorded at the sealed digest, and `none` means no verdict has landed for that digest yet. Only an authoring run removes a bundle from this lane, so removal waits for the next one.

| uuid | Verdict | Sealed digest | Stream |
| --- | --- | --- | --- |
| 2e9347cf-a1c9-596f-8a35-4f52a3d1be12 | none | absent | none |
| 4a422020-1f29-57b5-8ed5-7229b0869e45 | none | absent | none |
| a4d65ca3-131e-5925-aa6b-0da8634389ca | none | absent | none |
| c02572c7-f19f-5fbb-a388-148fff09d488 | none | absent | none |
| d9358407-bdba-50a8-a473-f111aed43052 | none | absent | none |

## Coverage

| Keyword | Bundles |
| --- | --- |
| optimization | 5 |
| python | 5 |
| sweperf | 5 |

## Dataset structure

| Bundle | Task | Keywords | Registration | Sealed at | Tier |
| --- | --- | --- | --- | --- | --- |
| [`2e9347cf-a1c9-596f-8a35-4f52a3d1be12`](2e9347cf-a1c9-596f-8a35-4f52a3d1be12/) | `swe-perf/pallets__jinja-1516` | optimization, python, sweperf | unregistered | unsealed | - |
| [`4a422020-1f29-57b5-8ed5-7229b0869e45`](4a422020-1f29-57b5-8ed5-7229b0869e45/) | `swe-perf/networkx__networkx-8296` | optimization, python, sweperf | unregistered | unsealed | - |
| [`a4d65ca3-131e-5925-aa6b-0da8634389ca`](a4d65ca3-131e-5925-aa6b-0da8634389ca/) | `swe-perf/networkx__networkx-7971` | optimization, python, sweperf | unregistered | unsealed | - |
| [`c02572c7-f19f-5fbb-a388-148fff09d488`](c02572c7-f19f-5fbb-a388-148fff09d488/) | `swe-perf/networkx__networkx-6337` | optimization, python, sweperf | unregistered | unsealed | - |
| [`d9358407-bdba-50a8-a473-f111aed43052`](d9358407-bdba-50a8-a473-f111aed43052/) | `swe-perf/networkx__networkx-8615` | optimization, python, sweperf | unregistered | unsealed | - |

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#131a33","primaryTextColor":"#e8ecff","primaryBorderColor":"#845EF7","lineColor":"#22d3ee","fontFamily":"monospace"}}}%%
flowchart LR
    bundle["&lt;uuid&gt;/"]
    bundle --> n0["task.toml<br/>runner manifest"]
    bundle --> n1["instruction.md<br/>objective the agent reads"]
    bundle --> n2["environment/<br/>agent sandbox image"]
    bundle --> n3["tests/<br/>verifier, hidden from the agent"]
    bundle --> n4["solution/<br/>private oracle"]
    bundle --> n5["uuid_provenance.json"]
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
  title  = {Kraken: A Repository-Level Performance Optimization RL Environment},
  author = {{Ethara.AI}},
  year   = {2026},
  note   = {Grounded in SWE-fficiency (Ma et al., arXiv:2511.06090). Signed genesis digest sha256:9b38b6817e2a995c12657e4157f5ac6dd1582131698c9bc96ed10a6d4df7dafa. Available at https://github.com/Ethara-Ai/kraken.}
}
```

## License

Kraken is released under the MIT License, Copyright (c) 2026 Ethara.AI. The full text lives at [LICENSE](LICENSE).

## Contact

- Organization: Ethara.AI at <https://github.com/Ethara-Ai>
- Security disclosures: `security@ethara.ai`; the report classes, response targets, and safe-harbor terms are stated once in [SECURITY.md](SECURITY.md).
- Contribution route: entry rules and the where-changes-go routing are stated in [CONTRIBUTING.md](CONTRIBUTING.md); ownership by path is declared in [.github/CODEOWNERS](.github/CODEOWNERS).
