# License and provenance notice

This task is derived from the Cirq project (https://github.com/quantumlib/Cirq),
Copyright The Cirq Developers, licensed under the Apache License, Version 2.0. The
starter tree is Cirq at commit 0fe0535e1fc206f0bfeabb3437e9753676d187a1. The task follows
upstream pull request #8197, "Speed up merging single qubit gates to phxz via transformers"
(merge commit 5539290c459696f14043a973dfab11df48a69867): the visible workload follows the
benchmark that pull request adds, and the verifier uses that commit's versions of three
covering test files. The reference solution (`solution/reference.patch`, laid over the base
tree as `tests/expert/` for timing) is a fast reference implementation written for this
task as a modification of Cirq's library source; it goes further than the pull request and
is distributed under the same license. The Apache-2.0 license text applies to that code:
https://www.apache.org/licenses/LICENSE-2.0

Contamination note: the upstream fix is a public commit (merged 2026-08-01). Buyers
evaluating models trained after that date should treat the task as potentially seen;
reproducing that fix alone does not reach the reference speed.
