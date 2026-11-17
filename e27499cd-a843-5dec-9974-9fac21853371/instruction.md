# Speed up scikit-learn's coordinate descent regularization paths

## Background

A development checkout of scikit-learn lives at `/app/scikit-learn`. It is installed
in editable mode with meson-python: the `python` on your `PATH` imports `sklearn` from
that tree, and a saved change to a `.py` or `.pyx` file under `/app/scikit-learn/sklearn/` is recompiled
automatically on the next `import sklearn` (the first import after a Cython change
takes a minute or so). The compiler toolchain is installed. The tree has its own test
suite; run it with `python -m pytest /app/scikit-learn/sklearn/linear_model/tests` from
`/app/scikit-learn`.

Fitting a regularization path with the coordinate descent solvers
(`sklearn.linear_model.enet_path`, `lasso_path`, and the cross-validated estimators
built on them) is slower than it needs to be. On long paths much of the time is
spent outside the coordinate updates themselves, and on some kinds of input far more
than on others.

## Seeing the problem

```
python /app/workload/path_workload.py
```

The script fits a few paths and cross-validated models on synthetic problems drawn
from one fixed seed and prints the wall-clock time and a digest of the coefficients
of each.

## What to deliver

Change scikit-learn's library source so that fitting these paths is much faster.
The work is done when all of these hold:

1. **Faster on problems beyond the script's.** Not only the ones in the script: any
   sizes, densities, penalties and seeds (tolerances `tol` between `1e-3` and
   `5e-3`, between 60 and 400 alphas per path), on these three kinds of input:
   - **dense inputs:** `enet_path` and `lasso_path` with `precompute=False`, and
     `ElasticNetCV` and `LassoCV` with `precompute=False`, on dense `X` with many
     more samples than features;
   - **multi-task models on sparse inputs:** `MultiTaskElasticNetCV` and
     `MultiTaskLassoCV` on `scipy.sparse` CSC `X`, with `fit_intercept=True` and with
     `fit_intercept=False`, with and without `sample_weight`;
   - **single-output sparse inputs and Gram matrices:** `ElasticNetCV` and
     `LassoCV` on `scipy.sparse` CSC `X`, with `fit_intercept=True` and with
     `fit_intercept=False`, with and without `sample_weight`; and `enet_path` with a
     precomputed Gram matrix (`precompute=<array>` and `Xy` given) on dense `X` with
     more samples than features.
2. **Same results as now.** For every input above, every array the call returns or
   the fitted estimator holds (path coefficients, dual gaps, `coef_`, `intercept_`,
   `mse_path_`, `dual_gap_`) must match what the unmodified library returns within
   `max|a - b| <= 1e-6 * max|a|` (`a` being the unmodified result); the numbers of
   iterations (`n_iters` of a path, `n_iter_`) must be equal; and the alpha grid, the
   selected `alpha_` and `l1_ratio_` must be equal within a relative `1e-9`.
3. **Your change must build** from source with the same toolchain.
4. **The existing tests still pass**: every test under
   `/app/scikit-learn/sklearn/linear_model/tests` that passes now, in particular all of
   `/app/scikit-learn/sklearn/linear_model/tests/test_coordinate_descent.py` and
   `/app/scikit-learn/sklearn/linear_model/tests/test_sparse_coordinate_descent.py`.
   The public call signatures of
   `sklearn.linear_model` (its functions and its estimators' `__init__`, `fit`,
   `path`, `predict` and `score`) must stay exactly as they are; private Cython
   functions may change.
5. **The patch looks like normal upstream work.** In particular:
   - keep the diff to the coordinate descent machinery (the Cython solvers in
     `/app/scikit-learn/sklearn/linear_model/_cd_fast.pyx`, the path and estimator code
     in `/app/scikit-learn/sklearn/linear_model/_coordinate_descent.py` that drives
     them, and any build
     file entry a new helper needs), with no unrelated rewrites, reformatting or dead
     code;
   - document every parameter you add to a solver or helper in its docstring (what it
     holds, its shape, and what happens when it is not given), make every comment you
     add or change describe what the new code does, and leave no docstring or comment
     describing behaviour the code no longer has;
   - any solver in `/app/scikit-learn/sklearn/linear_model/_cd_fast.pyx` that you let
     receive state computed elsewhere must
     still work when called without it, computing that state itself, so a direct call
     with today's arguments behaves as before;
   - add no module-level, class-level or function-attribute caches that keep
     residuals, column norms, Gram products, coefficients or fitted paths from one
     call of a public function or `fit` for a later call.

## Constraints

- Only library source under `/app/scikit-learn/sklearn/` may change, and not its test
  directories (every `tests` directory under it), the pytest conftest modules under
  `/app/scikit-learn` (for example `/app/scikit-learn/sklearn/conftest.py`),
  `/app/scikit-learn/sklearn/utils/_testing.py`,
  `/app/scikit-learn/sklearn/utils/estimator_checks.py` or
  `/app/scikit-learn/sklearn/utils/_test_common/`. Leave the workload script
  `/app/workload/path_workload.py` and the top-level build and test settings
  (`/app/scikit-learn/pyproject.toml`, `/app/scikit-learn/meson.build`, and any
  requirements and lock files) alone.
  Do not change files outside `/app/scikit-learn/sklearn/` (for example under
  `/app/scikit-learn/doc/`).
- No state may survive between calls, runs or processes to speed up later calls,
  whether through files, shared memory, a resident process or anything similar.
- Keep each call single-threaded: no threads, processes or multi-threaded BLAS or
  OpenMP inside a call.
- Code must not change its behaviour based on the call stack, environment variables,
  command-line arguments, the user or home directory, timers, or files outside the
  library.
- Solve the slowdown generally: choose code paths from properties of the input, never
  from the script's particular problems, sizes or seed.
- The sandbox is offline. Do not install, reinstall or upgrade packages.
