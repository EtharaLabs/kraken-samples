# Golden trajectory, ethara/15cc24a8-079f-5afc-98d3-ab0344dd7338

The ordered path a solver walks through `instruction.md`. Each step names the action, the state it establishes, and the checker identifier it satisfies. Every deliverable and every red line of the bound contract appears as a step, and every step binds one.

## Deliverable

- **D1**, the modified scikit-learn working tree at `/app/scikit-learn`. Harbor snapshots it out of the agent container and re-materializes it in the separate verifier, which overlays its `sklearn/` changes on a warm base tree and rebuilds it from source.

## Ordered path

1. **Read the statement and see the problem.** `instruction.md` points at `python /app/workload/path_workload.py`, which fits a few paths and cross-validated models from one fixed seed and prints their times and coefficient digests. Profiling a long path shows most of the time is spent outside the coordinate updates: per-alpha setup of residuals, column norms and dual gaps, and on sparse inputs with an intercept far more than on dense ones.

   - establishes: the per-alpha work around the coordinate updates, not the updates, is the target
   - satisfies: none yet; this is the discovery step the archetype measures

2. **Carry solver state across the whole path.** The change belongs in the Cython solvers of `sklearn/linear_model/_cd_fast.pyx` and the path code of `sklearn/linear_model/_coordinate_descent.py` that drives them: residuals, the products X.T @ R and Q @ w, and the column norms stay valid from one alpha to the next instead of being recomputed, sparse centering folds into a scalar offset, and the dual gap is computed only when it decides convergence. Dense tall inputs fitted with precompute=False may run the same coordinate descent on rows of X.T @ X filled on demand, without turning the user's flag into a Gram argument.

   - establishes: the cost of a path no longer grows by a full setup per alpha
   - satisfies: F1, F2, F3

3. **Keep every result identical to the unmodified library.** For every timed case of every family, every array the call returns or the fitted estimator holds (path coefficients, dual gaps, coef_, intercept_, mse_path_, dual_gap_) matches the unmodified library within max|a - b| <= 1e-6 * max|a|, the numbers of iterations are equal, and the alpha grid, the selected alpha_ and l1_ratio_ are equal within a relative 1e-9.

   - establishes: the gate check G-EQUIV holds on every case of every family
   - satisfies: the gate, and with it every graded item

4. **Make the change build.** The base source with the submission's sklearn/ changes overlaid rebuilds with the same meson-python toolchain; a tree that does not compile scores 0.

   - establishes: the overlaid tree compiles in the verifier
   - satisfies: the gate check G-BUILD

5. **Keep the repository's own tests passing and the public signatures unchanged.** Every test under sklearn/linear_model/tests that passes on the base build, and every test of test_coordinate_descent.py and test_sparse_coordinate_descent.py, passes on the graded tree. The public call signatures of sklearn.linear_model stay exactly as they are; private Cython functions may change.

   - establishes: the library still behaves as its own suite requires
   - satisfies: the gate check G-TESTS

6. **Keep every solver callable on its own.** Any solver in `_cd_fast.pyx` that now receives state computed elsewhere still works when called without it, computing that state itself, so a direct call with today's arguments behaves as before.

   - establishes: the solvers stay standalone private API
   - satisfies: d1_robustness_standalone_solver

7. **Earn the speed on unseen problems, in fresh processes.** Every timing runs in a fresh process with single-threaded BLAS and OpenMP after a warm-up call on a tiny problem, rotated across base, reference and submission builds, so no side warms a cache for another. Each family draws grading-time seeds, so the timed problems are never the ones the visible script builds. The statistic is T is the median of the repeated timings of the case; the case score is clamp(ln(T_base / T_sub) / ln(T_base / T_ref), 0, 1), and the family score is the median of its scored case scores.

   - establishes: the measured gain is a property of the code, not of the harness or of the visible script
   - satisfies: F1, F2, F3, and the red lines RL2 and RL4

8. **Stay inside the editable surface and tell nothing about the grader.** /app/scikit-learn/sklearn/ library source only. Test directories, conftest.py files, sklearn/utils/_testing.py, sklearn/utils/estimator_checks.py and sklearn/utils/_test_common/ are protected, and so are benchmarks/, asv_benchmarks/, build_tools/, maint_tools/ and the top-level build and test settings; changes outside sklearn/ are ignored. No state survives between runs or processes, and no added line reads the call stack, the process environment, the command line, the user or home directory, or the grader's files.

   - establishes: the gate check G-RL holds, so no red line is recorded
   - satisfies: the red lines RL1, RL2 and RL3

9. **Leave a diff an upstream reviewer would accept.** The diff stays inside the coordinate descent machinery with no unrelated rewrite, reformatting or dead code; every parameter it adds is documented in its docstring and every comment describes what the new code does; and no module-level, class-level or function-attribute state keeps residuals, norms, Gram products, coefficients or paths from one call for a later one.

   - establishes: the judged share of the reward is earned
   - satisfies: d1_craft_diff_scope, d1_craft_docs_match, d1_robustness_standalone_solver, rl2_process_global_cache, rl4_robustness_visible_special_case

## Red lines, each as its own step

- **RL1.** Only library source under /app/scikit-learn/sklearn/ may change, and no protected path Established by: treeops builds the graded tree from the base source and the submission's sklearn/ changes; a changed path matching the protected pattern is recorded as an edited protected path and never reaches the graded tree.
- **RL2.** No state survives between runs or processes to flatter repeated timings, whether through files, shared memory, a resident process or anything similar Established by: a line-level scan of the added lines for persistence constructs, plus a check for files left outside the run scratch by any timed child.
- **RL3.** Code must not try to tell when it is being graded, for example by reading the call stack, the process environment, the command line, the user or home directory, or the grader's files Established by: a line-level scan of the added lines for stack, environment, argv, uid and grader-path constructs.
- **RL4.** Nothing may be tailored to the visible workload script's particular problems, sizes, tolerance or seed Established by: a line-level scan of the added lines for the visible workload literals of tests/harness/config.json, and every timed case draws a fresh grading-time seed.

## Checker identifiers this path satisfies

- `F1` (F1, obligation D1, dimension outcome, compiled, weight 3): On enet_path, lasso_path, ElasticNetCV and LassoCV with precompute=False over dense X with many more samples than features, drawn at grading time, the submission's median time per case clears the base median by more than the family's measured noise band, and the family score is the median over its scored cases of clamp(ln(T_base / T_sub) / ln(T_base / T_ref), 0, 1).
- `F2` (F2, obligation D1, dimension outcome, compiled, weight 5): On MultiTaskElasticNetCV and MultiTaskLassoCV over scipy.sparse CSC X, with and without an intercept and with and without sample weights, drawn at grading time, the submission's median time per case clears the base median by more than the family's measured noise band, and the family score is the median over its scored cases of clamp(ln(T_base / T_sub) / ln(T_base / T_ref), 0, 1).
- `F3` (F3, obligation D1, dimension coverage, compiled, weight 3): The speedup reaches the single-output sparse and Gram solvers and not only the dense path: ElasticNetCV and LassoCV on sparse X with and without an intercept and sample weights, and enet_path with a precomputed Gram matrix, all clear the family's measured noise band, and the family score is the median over its scored cases of clamp(ln(T_base / T_sub) / ln(T_base / T_ref), 0, 1).
- `d1_craft_diff_scope` (d1_craft_diff_scope, obligation D1, dimension craft, judged, weight 1): The diff is confined to scikit-learn's coordinate descent machinery: the Cython solvers in sklearn/linear_model/_cd_fast.pyx, the path and estimator code in sklearn/linear_model/_coordinate_descent.py that drives them, and any build-file entry a new helper needs. It carries no unrelated rewrites, reformatting or dead code (unused helpers, unreachable branches, commented-out code).
- `d1_craft_docs_match` (d1_craft_docs_match, obligation D1, dimension craft, judged, weight 1): Every parameter the diff adds to a solver or helper is described in that function's docstring (what it holds, its shape, and what happens when it is not given), every comment the diff adds or changes describes what the new code actually does, and no existing docstring or comment is left describing behaviour the code no longer has.
- `d1_robustness_standalone_solver` (d1_robustness_standalone_solver, obligation D1, dimension robustness, judged, weight 1): Every solver function in _cd_fast.pyx that the diff lets receive state computed elsewhere (for example residuals, column norms or Gram products) can still be called without that state, in which case it computes it itself, so a direct call with the previous arguments behaves as before.
- `rl2_process_global_cache` (rl2_process_global_cache, obligation RL2, dimension process, judged, weight 1, prohibition): The diff adds module-level, class-level or function-attribute state (for example a dict, lru_cache, functools.cache or a global array) that keeps residuals, column norms, Gram products, coefficients or fitted paths from one call of a public function or fit for reuse by a later call.
- `rl4_robustness_visible_special_case` (rl4_robustness_visible_special_case, obligation RL4, dimension robustness, judged, weight 1, prohibition): The diff special-cases the visible workload rather than speeding up the general path: it branches on its problem sizes, its number of alphas, its tolerance, its seed, or a threshold tuned to that script.

- the gate: The reward is 0 when a red line RL1 to RL4 fired, the overlaid tree failed to build, or a covering test failed. Inside an open gate each family score S_f is itself 0 when any case of that family is not equivalent to the base output or the submission's run for that family failed.
- the gate check `G-BUILD` (obligation D1, carrier `tests/harness/build.py`): The base source with the submission's sklearn/ changes overlaid rebuilds with the same meson-python toolchain; a tree that does not compile scores 0.
- the gate check `G-EQUIV` (obligation D1, carrier `tests/harness/equiv.py`): For every timed case of every family, every array the call returns or the fitted estimator holds (path coefficients, dual gaps, coef_, intercept_, mse_path_, dual_gap_) matches the unmodified library within max|a - b| <= 1e-6 * max|a|, the numbers of iterations are equal, and the alpha grid, the selected alpha_ and l1_ratio_ are equal within a relative 1e-9.
- the gate check `G-TESTS` (obligation D1, carrier `tests/harness/repotests.py`): Every test under sklearn/linear_model/tests that passes on the base build, and every test of test_coordinate_descent.py and test_sparse_coordinate_descent.py, passes on the graded tree.
- the gate check `G-RL` (obligation RL1, carrier `tests/harness/treeops.py`): No red line RL1 to RL4 is recorded in the measurement record.

## The three timed families

- **F1** (weight 0.25, 8 hidden cases), enet_path, lasso_path, ElasticNetCV and LassoCV with precompute=False: dense X with many more samples than features.
- **F2** (weight 0.4, 8 hidden cases), MultiTaskElasticNetCV and MultiTaskLassoCV: scipy.sparse CSC X, with fit_intercept=True and fit_intercept=False, with and without sample_weight.
- **F3** (weight 0.2, 8 hidden cases), ElasticNetCV and LassoCV on sparse X, and enet_path with a precomputed Gram matrix: scipy.sparse CSC X with and without an intercept and sample weights, and dense X with more samples than features passed with precompute=<array> and Xy.

The noise band is per family, the largest ln spread of the base build's own repeated timings, clamped to the closed interval from 0.05 to 0.15. A speedup over base at or below the band scores 0, and a submission within the band of the reference scores 1. A case whose reference gain ln(T_base / T_ref) is at or below twice the band is not scored.

## Rejected routes

- **public_fix_only** (K3): Reward about 0.318: the upstream pull request alone does not reach the reference speed, so memorisation of the public fix does not saturate the reward
- **precompute_flag_changed** (K4): A submission that turns precompute=False into a user-visible Gram argument or loosens tol or max_iter moves results or iteration counts, fails G-EQUIV on the cases it touches, and zeroes those families
- **global_cache** (K5): Reward 0 or near it: the leftover check and the line scan record RL2, which closes the gate
- **visible_special_case** (K6): Reward 0 on the literal route (RL4 recorded) and no speedup on the hidden route, because the grading-time seeds are never the visible one
- **protected_edit** (K7): Reward 0: an edit to a test directory, conftest.py, a test helper or a build setting never reaches the graded tree and is recorded as RL1, which closes the gate

## Why the ordering is forced

The gate stands before every graded item, so a faster path that moves one coefficient, one iteration count or one selected alpha earns nothing and the equivalence step cannot be deferred. With no judge configured: reward = (0.25 S_F1 + 0.40 S_F2 + 0.20 S_F3) / 0.85. With a judge configured: reward = 0.25 S_F1 + 0.40 S_F2 + 0.20 S_F3 + 0.15 J. A red line, a failed build or a failed covering test sets the reward to 0. No term multiplies J by any speed score. The judged items are never multiplied by a family speed term, and an empty diff is never sent to the judge. The reference is a faster original whole-path implementation rather than the public upstream fix, so reproducing the public fix lands partway up the ladder instead of at the top.

Revision note (2026-11-16): re-sent with the revision 3 task files (no agents baked into the image, no-network for the environment and the agent) and a verifier image that ends as root, the setup of 015a6071 and 87ec7a10.

Revision note (2026-11-17): the compilers come from the full python:3.13 trixie image; nothing is fetched with apt at build time, as in 015a6071 and 87ec7a10.
