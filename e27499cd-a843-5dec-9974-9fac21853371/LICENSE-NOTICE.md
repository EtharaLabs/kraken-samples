# License and provenance notice

This task is derived from the scikit-learn project (https://github.com/scikit-learn/scikit-learn),
licensed under the BSD 3-Clause License. The starter tree is scikit-learn at commit
9ddf4d35c20f780451aefd1c94c268da6367e4de. The task follows upstream pull request #34572
(merged 2026-07-29 as 6f8b95aa2234102acc3804fc8c7a3e6bd0506bfb); the graded reference
(`solution/reference.patch`, also in `tests/expert/`) is a faster implementation written for
this task on top of that scikit-learn code. The BSD 3-Clause license text below applies to
that code.

Contamination note: the upstream pull request is public (merged 2026-07-29). Buyers evaluating
models trained after that date should treat the task as potentially seen; reproducing the
public fix alone does not reach the reference speed.

## scikit-learn license (COPYING at the base commit)

```
BSD 3-Clause License

Copyright (c) 2007-2026 The scikit-learn developers.
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

* Redistributions of source code must retain the above copyright notice, this
  list of conditions and the following disclaimer.

* Redistributions in binary form must reproduce the above copyright notice,
  this list of conditions and the following disclaimer in the documentation
  and/or other materials provided with the distribution.

* Neither the name of the copyright holder nor the names of its
  contributors may be used to endorse or promote products derived from
  this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```
