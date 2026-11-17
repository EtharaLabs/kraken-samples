# License and provenance notice

This task is derived from the Cirq project (https://github.com/quantumlib/Cirq),
licensed under the Apache License, Version 2.0. The starter tree is Cirq at commit
0fe0535e1fc206f0bfeabb3437e9753676d187a1. The task follows upstream pull request #8197
(merged 2026-08-01, 5539290c459696f14043a973dfab11df48a69867); the graded reference
(`solution/reference.patch`, also in `tests/expert/`) is a faster implementation written for
this task on top of that Cirq code. The Apache-2.0 license text applies to that code:
https://www.apache.org/licenses/LICENSE-2.0

Contamination note: the upstream pull request is public (merged 2026-08-01). Buyers evaluating
models trained after that date should treat the task as potentially seen; reproducing the
public fix alone does not reach the reference speed.
