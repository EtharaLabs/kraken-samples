# License and provenance notice

This task is derived from the NumPy project (https://github.com/numpy/numpy), licensed under the
BSD 3-Clause License. The starter tree is NumPy at commit
a73316f07a23323e3f86a861f967e2457277e903; the reference fix follows upstream pull request #32693
("ENH: allow StringDType to use the sort paths in isin", merged as
7643e77e8481c80472efb1c9d29de9898d765187), and the task extends it beyond that fix. The NumPy
license text applies to that code: https://github.com/numpy/numpy/blob/main/LICENSE.txt

Contamination note: the upstream part of the ground truth is a public commit (merged 2026-09-24).
Buyers evaluating models trained after that date should treat that part as potentially seen.
