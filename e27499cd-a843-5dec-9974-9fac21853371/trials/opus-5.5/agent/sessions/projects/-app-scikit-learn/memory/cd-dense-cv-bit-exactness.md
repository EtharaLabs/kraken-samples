---
name: cd-dense-cv-bit-exactness
description: Dense-X CV estimators (LassoCV etc.) pick alpha_ from last-bit noise on MSE plateaus; CD solver changes must keep dense coefficient paths bit-identical
metadata:
  node_type: memory
  type: project
  originSessionId: 22e4480a-939f-4b66-b23f-e6305c97de8c
  modified: 2026-11-17T10:29:31.333Z
---

In sklearn/linear_model CV estimators with dense X, `mse_path_` often has long plateaus (many alphas early-stop with n_iter=0, identical coef columns). `X_test @ coefs` (BLAS GEMM) adds ~1e-16 noise per column lane (blocks of 4), so the argmin, i.e. `alpha_`, is decided by last bits. Any 1-ulp change in dense coefficient paths flipped `alpha_` in ~15% of script-like problems (noise 0.1, 10% informative). Sparse X_test (scipy matvec) has no lane effect, so ties stay exact there.

**Why:** Task (2026-11-17) required `alpha_` to match the unmodified library within 1e-9.

**How to apply:** For the dense / dense multi-task CD solvers, carried state (R, X.T@R) may be used only for the pre-loop convergence check; recompute R exactly as the original before coordinate updates. Carrying R incrementally is fine for the sparse and Gram solvers when only tolerance checks apply. Verify with bitwise `np.array_equal` against a saved copy of the original module.
