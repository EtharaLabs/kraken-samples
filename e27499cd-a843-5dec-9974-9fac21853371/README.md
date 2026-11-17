# License and provenance notice

This task is derived from scikit-learn (https://github.com/scikit-learn/scikit-learn),
Copyright (c) 2007-2026 The scikit-learn developers, licensed under the BSD 3-Clause
License. The starter tree is scikit-learn at commit
9ddf4d35c20f780451aefd1c94c268da6367e4de. The task follows upstream pull request #34572,
"ENH precompute residual and column norm of X in coordinate descent" by Christian
Lorentzen (merge commit 6f8b95aa2234102acc3804fc8c7a3e6bd0506bfb). The reference
solution (`solution/reference.patch`, laid over the base tree as `tests/expert/` for
timing) is a fast reference implementation written for this task as a modification of
`sklearn/linear_model/_cd_fast.pyx` and `sklearn/linear_model/_coordinate_descent.py`; it
builds on that pull request, goes further than it, and is distributed under the same
license. The covering tests are the base commit's own test files. The BSD 3-Clause
license text that applies to that code ships with the source tree as `COPYING` and is at
https://github.com/scikit-learn/scikit-learn/blob/main/COPYING

Contamination note: the upstream fix is a public commit (merged 2026-07-29). Buyers
evaluating models trained after that date should treat the task as potentially seen;
reproducing that fix alone does not reach the reference speed.
