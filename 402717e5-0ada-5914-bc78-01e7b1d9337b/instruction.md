# Speed up the Zivot-Andrews unit-root test in statsmodels

## Background

A development checkout of statsmodels lives at `/app/statsmodels`. It is built in
place, and the `python` interpreter on your `PATH` imports the library straight
from that tree, so a saved edit to a `.py` file is picked up by the next
interpreter you start. The test plugin named in the repository's pytest
`addopts` is not installed, so run tests with `-o addopts=""`, for example
`python -m pytest -o addopts="" /app/statsmodels/statsmodels/tsa/tests/test_stattools.py`.

`statsmodels.tsa.stattools.zivot_andrews` tests for a unit root in the presence
of one structural break at an unknown date. On long series it is very slow, and
its running time grows much faster than the length of the series.

## Seeing the problem

```
python /app/workload/za_workload.py
```

The script builds one seeded series of a few thousand observations, calls
`zivot_andrews` once in a fresh interpreter, and prints how long the call took
and every value it returned.

## What to deliver

Change library code in `/app/statsmodels/statsmodels/tsa/` (outside its `tests`
directories) so that `zivot_andrews` is as fast as you can make it on long
series. Changes anywhere else in the checkout are discarded.

It must be fast beyond the visible script: on other series, from any seed, at
other lengths (both much shorter and much longer than the script's), with every `regression`
option, every `autolag` option including `None`, several `trim` values, and
explicit `maxlag` values, on the first call on a series in a fresh Python
process, on one CPU core.

Results must stay what the current code returns:

1. For ordinary series, the statistic and p-value must match the current code
   to a relative tolerance of 1e-9, and the critical values, the number of lags
   and the break index must be identical, except that the break index (or the
   lag) may differ where the two best candidates are tied to within that same
   relative tolerance.
2. For series whose regressors are close to collinear, the reference is an
   exact high-accuracy least-squares fit of every candidate period rather than
   the current code, compared to a relative tolerance of 1e-6. Being more
   accurate than the current code there is fine; being less accurate is not.
3. Inputs the current code rejects must raise the same exception type with the
   same message, and difficult inputs (non-finite values, singular or nearly
   singular regressors, break dummies that are all zero, wrap around, or lie in
   the span of the other regressors, a trim of 0) must give the same result,
   exception and warnings as the current code, or the high-accuracy result.
4. The existing tests of `/app/statsmodels/statsmodels/tsa/tests/test_stattools.py`
   and `/app/statsmodels/statsmodels/tsa/tests/test_lagselect.py` must still pass.

The change itself must also meet these expectations:

- Keep the existing fallback path working and readable: the current way of
  computing the result must stay in place for the inputs a faster path cannot
  handle, and the conditions that send a call to it must be written out plainly.
- Solve the problem generally, not for particular inputs: choose code paths and
  constants from general numerical conditions, never from particular series
  lengths, option combinations or trim values.
- Keep the change to the Zivot-Andrews code path and the helpers it calls, with
  no unrelated refactoring, reformatting or renaming.
- Leave no dead or misleading code: no unused helpers or imports, no
  commented-out code, and no comments that misstate what the code does; explain
  any new algebra well enough for a maintainer to check it.
- Keep the linear algebra numerically stable, without explicit inverses of
  cross-product matrices or normal-equation solves.

## Rules

- RL1: do not edit tests, benchmarks, `/app/statsmodels/statsmodels/conftest.py`,
  the workload script `/app/workload/za_workload.py`, or test and build
  configuration (`/app/statsmodels/pyproject.toml`, `/app/statsmodels/meson.build`,
  the other meson build files under `/app/statsmodels` and the like).
- RL2: do not keep computed results between `zivot_andrews` calls, timing runs or
  processes, whether in files, shared memory, module-level state or a resident
  process. Reusing work inside one call is fine.
- RL3: do not change behaviour based on the call stack, environment variables,
  command-line arguments, file paths or files outside the library.
- RL4: do not special-case the visible script's inputs, size, seed or output.
- RL5: use one CPU core inside a call: no threads, processes or multi-threaded
  BLAS.
- RL6: do not add compiled extensions, `.pth` files, `sitecustomize` or
  `usercustomize`, and do not patch numpy, scipy or the timer.

The sandbox is offline. Do not install, reinstall or upgrade packages.
