# Authors: The scikit-learn developers
# SPDX-License-Identifier: BSD-3-Clause

from libc.math cimport fabs, sqrt, INFINITY
import numpy as np

from cython cimport floating
import warnings
from sklearn.exceptions import ConvergenceWarning

from sklearn.utils._cython_blas cimport (
    _axpy, _dot, _asum, _gemv, _nrm2, _copy, _scal
)
from sklearn.utils._cython_blas cimport ColMajor, Trans, NoTrans
from sklearn.utils._typedefs cimport int32_t, uint8_t, uint32_t, uint64_t
from sklearn.utils._random cimport our_rand_r


cdef extern from "<float.h>":
    const float FLT_EPSILON
    const double DBL_EPSILON

# The following two functions are shamelessly copied from the tree code.

cdef enum:
    # Max value for our rand_r replacement (near the bottom).
    # We don't use RAND_MAX because it's different across platforms and
    # particularly tiny on Windows/MSVC.
    # It corresponds to the maximum representable value for
    # 32-bit signed integers (i.e. 2^31 - 1).
    RAND_R_MAX = 2147483647


cdef inline uint32_t rand_int(uint32_t end, uint32_t* random_state) noexcept nogil:
    """Generate a random integer in [0; end)."""
    return our_rand_r(random_state) % end


cdef inline floating fmax(floating x, floating y) noexcept nogil:
    if x > y:
        return x
    return y


cdef inline floating fsign(floating f) noexcept nogil:
    if f == 0:
        return 0
    elif f > 0:
        return 1.0
    else:
        return -1.0


cdef inline floating abs_max(int n, const floating* a) noexcept nogil:
    """np.max(np.abs(a))"""
    cdef int i
    cdef floating m = fabs(a[0])
    cdef floating d
    for i in range(1, n):
        d = fabs(a[i])
        if d > m:
            m = d
    return m


cdef inline floating max(int n, floating* a) noexcept nogil:
    """np.max(a)"""
    cdef int i
    cdef floating m = a[0]
    cdef floating d
    for i in range(1, n):
        d = a[i]
        if d > m:
            m = d
    return m


cdef inline floating diff_abs_max(int n, const floating* a, floating* b) noexcept nogil:
    """np.max(np.abs(a - b))"""
    cdef int i
    cdef floating m = fabs(a[0] - b[0])
    cdef floating d
    for i in range(1, n):
        d = fabs(a[i] - b[i])
        if d > m:
            m = d
    return m


cdef inline floating sparse_dot(
    int32_t j,
    const floating[::1] X_data,  # in
    const int32_t[::1] X_indices,  # in
    const int32_t[::1] X_indptr,  # in
    const floating[::1] y,
) noexcept nogil:
    """BLAS X[:, j] @ y for sparse CSC X."""
    cdef int32_t i, i_ind
    cdef int32_t startptr = X_indptr[j]
    cdef int32_t endptr = X_indptr[j + 1]
    cdef floating result = 0

    for i_ind in range(startptr, endptr):
        i = X_indices[i_ind]
        result += X_data[i_ind] * y[i]
    return result


cdef inline floating sparse_axpy(
    int32_t j,
    floating a,
    const floating[::1] X_data,  # in
    const int32_t[::1] X_indices,  # in
    const int32_t[::1] X_indptr,  # in
    floating[::1] y,  # out
) noexcept nogil:
    """BLAS y += a * X[:, j] for sparse CSC X."""
    cdef int32_t i, i_ind
    cdef int32_t startptr = X_indptr[j]
    cdef int32_t endptr = X_indptr[j + 1]

    for i_ind in range(startptr, endptr):
        i = X_indices[i_ind]
        y[i] += a * X_data[i_ind]


message_conv = (
    "Objective did not converge. You might want to increase "
    "the number of iterations, check the scale of the "
    "features or consider increasing regularisation."
)


message_ridge = (
    "Linear regression models with a zero l1 penalization "
    "strength are more efficiently fitted using one of the "
    "solvers implemented in "
    "sklearn.linear_model.Ridge/RidgeCV instead."
)


def R_and_X_colnorm2(
    const floating[::1] w,
    const floating[::1, :] X,
    const floating[::1] y,
):
    """Compute residuals and squared column norms of X.

    Parameters
    ----------
    w : memoryview of shape (n_features,)
        Coefficients.

    X : memoryview of shape (n_samples, n_features), Fortran-contiguous
        Training data.

    y : memoryview of shape (n_samples,)
        Target values.

    Returns
    -------
    R : memoryview of shape (n_samples,)
        Residuals: R = y - X @ w

    norm2_cols_X : memoryview of shape (n_features,)
        Column norms of X: norm2_cols_X = np.sum(X**2, axis=0)
    """
    if floating is float:
        dtype = np.float32
    else:
        dtype = np.float64
    cdef unsigned int n_samples = y.shape[0]
    cdef unsigned int n_features = w.shape[0]

    cdef floating[::1] R = np.empty_like(y)
    cdef floating[::1] norm2_cols_X = np.einsum(
        "ij,ij->j", X, X, dtype=dtype, order="C"
    )
    # R = y - np.dot(X, w)
    _copy(n_samples, &y[0], 1, &R[0], 1)
    _gemv(ColMajor, NoTrans, n_samples, n_features, -1.0, &X[0, 0],
          n_samples, &w[0], 1, 1.0, &R[0], 1)

    return R, norm2_cols_X


cdef inline floating dual_gap_formulation_A(
    floating alpha,  # L1 penalty
    floating beta,  # L1 penalty
    floating w_l1_norm,
    floating w_l2_norm2,
    floating R_norm2,  # R @ R
    floating Ry,  # R @ y
    floating dual_norm_XtA,
    bint gap_smaller_eps,
) noexcept nogil:
    """Compute dual gap according to formulation A."""
    cdef floating gap, primal, dual
    cdef floating scale  # Scaling factor to achieve dual feasible point.

    if floating is float:
        eps = FLT_EPSILON
    else:
        eps = DBL_EPSILON

    primal = 0.5 * (R_norm2 + beta * w_l2_norm2) + alpha * w_l1_norm

    if (dual_norm_XtA > alpha):
        scale = alpha / dual_norm_XtA
    else:
        scale = 1.0
    dual = -0.5 * (scale ** 2) * (R_norm2 + beta * w_l2_norm2) + scale * Ry
    gap = primal - dual
    if gap_smaller_eps and abs(gap) <= 2 * eps * primal:
        gap = 0.0
    return gap


cdef (floating, floating) gap_enet(
    int n_samples,
    int n_features,
    const floating[::1] w,
    floating alpha,  # L1 penalty
    floating beta,  # L2 penalty
    const floating[::1, :] X,
    const floating[::1] y,
    const floating[::1] R,  # current residuals = y - X @ w
    floating[::1] XtA,  # XtA = X.T @ R - beta * w is calculated inplace
    bint positive,
    bint gap_smaller_eps,
) noexcept nogil:
    """Compute dual gap for use in enet_coordinate_descent.

    alpha > 0:            formulation A of the duality gap
    alpha = 0 & beta > 0: formulation B of the duality gap
    alpha = beta = 0:     OLS first order condition (=gradient)

    gap_smaller_eps: If 1 (True), set the dual gap to zero when the gap is around
        machine precision compared to primal. As gap = primal - dual, we might get
        gap != 0 in floating point arithmetic, while exact arithmetic would yield
        gap = 0.
    """
    cdef floating gap, primal, dual
    cdef floating dual_norm_XtA
    cdef floating R_norm2
    cdef floating Ry
    cdef floating w_l1_norm
    cdef floating w_l2_norm2 = 0.0

    if floating is float:
        eps = FLT_EPSILON
    else:
        eps = DBL_EPSILON

    # w_l2_norm2 = w @ w
    if beta > 0:
        w_l2_norm2 = _dot(n_features, &w[0], 1, &w[0], 1)
    # R_norm2 = R @ R
    R_norm2 = _dot(n_samples, &R[0], 1, &R[0], 1)
    # Ry = R @ y
    if not (alpha == 0 and beta == 0):
        Ry = _dot(n_samples, &R[0], 1, &y[0], 1)

    if alpha == 0:
        # XtA = X.T @ R
        _gemv(
            ColMajor, Trans, n_samples, n_features, 1.0, &X[0, 0],
            n_samples, &R[0], 1, 0, &XtA[0], 1,
        )
        # ||X'R||_2^2
        dual_norm_XtA = _dot(n_features, &XtA[0], 1, &XtA[0], 1)
        if beta == 0:
            # This is OLS, no dual gap available. Resort to first order condition
            #     X'R = 0
            #     gap = ||X'R||_2^2
            # Compare with stopping criterion of LSQR.
            gap = dual_norm_XtA
            return gap, dual_norm_XtA
        # This is Ridge regression, we use formulation B for the dual gap.
        primal = 0.5 * (R_norm2 + beta * w_l2_norm2)
        dual = -0.5 * R_norm2 + Ry - 1 / (2 * beta) * dual_norm_XtA
        gap = primal - dual
        if gap_smaller_eps and abs(gap) <= 2 * eps * primal:
            gap = 0.0
        return gap, dual_norm_XtA

    # XtA = X.T @ R - beta * w
    _copy(n_features, &w[0], 1, &XtA[0], 1)
    _gemv(ColMajor, Trans, n_samples, n_features, 1.0, &X[0, 0],
          n_samples, &R[0], 1,
          -beta, &XtA[0], 1)

    # dual_norm_XtA
    if positive:
        dual_norm_XtA = max(n_features, &XtA[0])
    else:
        dual_norm_XtA = abs_max(n_features, &XtA[0])

    # w_l1_norm = np.sum(np.abs(w))
    w_l1_norm = _asum(n_features, &w[0], 1)

    gap = dual_gap_formulation_A(
        alpha=alpha,
        beta=beta,
        w_l1_norm=w_l1_norm,
        w_l2_norm2=w_l2_norm2,
        R_norm2=R_norm2,
        Ry=Ry,
        dual_norm_XtA=dual_norm_XtA,
        gap_smaller_eps=gap_smaller_eps,
    )
    return gap, dual_norm_XtA


def enet_coordinate_descent(
    floating[::1] w,
    floating alpha,
    floating beta,
    const floating[::1, :] X,
    const floating[::1] y,
    unsigned int max_iter,
    floating tol,
    object rng,
    bint random=0,
    bint positive=0,
    bint do_screening=1,
    bint early_stopping=1,
    floating[::1] R=None,
    floating[::1] norm2_cols_X=None,
):
    """
    Cython version of the coordinate descent algorithm for Elastic-Net regression.

    The algorithm mostly follows [Friedman 2010].
    We minimize the primal

        P(w) = 1/2 ||y - X w||_2^2 + alpha ||w||_1 + beta/2 ||w||_2^2

    The dual for beta = 0, see e.g. [Fercoq 2015] with v = alpha * theta, is

        D(v) = -1/2 ||v||_2^2 + y' v    (formulation A)

    with dual feasible condition ||X^T v||_inf <= alpha.
    For beta > 0, one uses extended versions of X and y by adding n_features rows

        X -> (           X)    y -> (y)
             (sqrt(beta) I)         (0)

    Note that the residual R = y - X w is an important ingredient for the estimation of
    a dual feasible point v.
    At optimum of primal w* and dual v*, one has

        v* = y - X w*

    The duality gap is

        G(w, v) = P(w) - D(v) <= P(w) - P(w*)

    Strong duality holds: G(w*, v*) = 0.
    For testing convergence, one uses G(w, v) with current w and uses

        v = R                            if ||X^T R||_inf <= alpha
        v = R * alpha / ||X^T R||_inf    else

    The final stopping criterion is based on the duality gap

        tol ||y||_2^2 <= G(w, v)

    The tolerance here is multiplied by ||y||_2^2 to have an inequality that scales the
    same on both sides and because one has G(0, 0) = 1/2 ||y||_2^2.

    Note:
    The above dual D(v) and duality gap G require alpha > 0 because of the dual
    feasible condition.
    There is, however, an alternative dual formulation, see [Dünner 2016] 5.2.3 and
    https://github.com/scikit-learn/scikit-learn/issues/22836:

        D(v) = -1/2 ||v||_2^2 + y' v
               -1/(2 beta) sum_j (|X_j' v| - alpha)_+^2    (formulation B)

    The dual feasible set is v element real numbers. It requires beta > 0, but
    alpha = 0 is allowed. Strong duality holds and at optimum, v* = y - X w*.

    Further Parameters
    ------------------
    random : bint, default=0 (False)
        If False, uses cyclic coordinate descent. If True, pick features at random.
    positive : bint, default=0 (False)
        If set to True, forces coefficients w to be positive.
    do_screening : bint, default=1 (True)
        If set to True, use gap safe screening rules to screen coefficients
        (exclude early based on dual gap).
    early_stopping : bint, default=1 (True)
        If set to True, check for convergence (with the dual gap) before entering the
        main iteration loop.
    R : memoryview or ndarray of shape (n_samples,) or None, default=None
        Initial value of the residual `R = y - X @ w`. If None, it will be computed.
    norm2_cols_X : memoryview or ndarray of shape (n_features,) or None, default=None
        Squared column norms of X. When R is None, R and norm2_cols_X are both computed
        and a given value is ignored; when R is given, norm2_cols_X must be given too.

    Returns
    -------
    w : ndarray of shape (n_features,)
        ElasticNet coefficients.
    gap : float
        Achieved dual gap.
    tol : float
        Equals input `tol` times `np.dot(y, y)`. The tolerance used for the dual gap.
    n_iter : int
        Number of coordinate descent iterations.

    References
    ----------
    .. [Friedman 2010]
       Jerome H. Friedman, Trevor Hastie, Rob Tibshirani. (2010)
       Regularization Paths for Generalized Linear Models via Coordinate Descent
       https://www.jstatsoft.org/article/view/v033i01

    .. [Fercoq 2015]
       Olivier Fercoq, Alexandre Gramfort, Joseph Salmon. (2015)
       Mind the duality gap: safer rules for the Lasso
       https://arxiv.org/abs/1505.03410

    .. [Dünner 2016]
       Celestine Dünner, Simon Forte, Martin Takác, Martin Jaggi. (2016).
       Primal-Dual Rates and Certificates. In ICML 2016.
       https://arxiv.org/abs/1602.05205
    """

    if floating is float:
        dtype = np.float32
    else:
        dtype = np.float64

    # get the data information into easy vars
    cdef unsigned int n_samples = X.shape[0]
    cdef unsigned int n_features = X.shape[1]

    cdef floating[::1] XtA = np.empty(n_features, dtype=dtype)

    cdef floating d_j
    cdef floating Xj_theta
    cdef floating tmp
    cdef floating w_j
    cdef floating d_w_max
    cdef floating w_max
    cdef floating d_w_j
    cdef floating gap = tol + 1.0
    cdef floating d_w_tol = tol
    cdef floating dual_norm_XtA
    cdef unsigned int n_active = n_features
    cdef uint32_t[::1] active_set
    # TODO: use binset instead of array of bools
    cdef uint8_t[::1] excluded_set
    cdef unsigned int j
    cdef unsigned int n_iter = 0
    cdef unsigned int f_iter
    cdef uint32_t rand_r_state_seed = rng.randint(0, RAND_R_MAX)
    cdef uint32_t* rand_r_state = &rand_r_state_seed

    if alpha == 0:
        # No screeing without L1-penalty.
        do_screening = False

    if do_screening:
        active_set = np.empty(n_features, dtype=np.uint32)  # map [:n_active] -> j
        excluded_set = np.empty(n_features, dtype=np.uint8)

    if R is None:
        # Initial value of the residuals. Will be kept up to date in the iterations.
        R, norm2_cols_X = R_and_X_colnorm2(w=w, X=X, y=y)

    with nogil:

        # tol *= np.dot(y, y)
        tol *= _dot(n_samples, &y[0], 1, &y[0], 1)

        # Check convergence before entering the main loop.
        # We want to avoid stopping too early and set gap_smaller_eps=False.
        gap, dual_norm_XtA = gap_enet(
            n_samples, n_features, w, alpha, beta, X, y, R, XtA, positive,
            gap_smaller_eps=False,
        )
        if early_stopping and gap <= tol:
            with gil:
                return np.asarray(w), gap, tol, 0

        # Gap Safe Screening Rules, see https://arxiv.org/abs/1802.07481, Eq. 11
        if do_screening:
            n_active = 0
            for j in range(n_features):
                if norm2_cols_X[j] == 0:
                    w[j] = 0
                    excluded_set[j] = 1
                    continue
                Xj_theta = XtA[j] / fmax(alpha, dual_norm_XtA)  # X[:,j] @ dual_theta
                d_j = (1 - fabs(Xj_theta)) / sqrt(norm2_cols_X[j] + beta)
                if d_j <= sqrt(2 * gap) / alpha:
                    # include feature j
                    active_set[n_active] = j
                    excluded_set[j] = 0
                    n_active += 1
                else:
                    if w[j] != 0:
                        # R += w[j] * X[:,j]
                        _axpy(n_samples, w[j], &X[0, j], 1, &R[0], 1)
                        w[j] = 0
                    excluded_set[j] = 1

        for n_iter in range(max_iter):
            w_max = 0.0
            d_w_max = 0.0
            for f_iter in range(n_active):  # Loop over coordinates
                if random:
                    j = rand_int(n_active, rand_r_state)
                else:
                    j = f_iter

                if do_screening:
                    j = active_set[j]

                if norm2_cols_X[j] == 0.0:
                    continue

                w_j = w[j]  # Store previous value

                # tmp = X[:,j] @ (R + w_j * X[:,j])
                tmp = _dot(n_samples, &X[0, j], 1, &R[0], 1) + w_j * norm2_cols_X[j]

                if positive and tmp < 0:
                    w[j] = 0.0
                else:
                    w[j] = (fsign(tmp) * fmax(fabs(tmp) - alpha, 0)
                            / (norm2_cols_X[j] + beta))

                if w[j] != w_j:
                    # R -= (w[j] - w_j) * X[:,j] # Update residual
                    _axpy(n_samples, w_j - w[j], &X[0, j], 1, &R[0], 1)

                # update the maximum absolute coefficient update
                d_w_j = fabs(w[j] - w_j)
                d_w_max = fmax(d_w_max, d_w_j)

                w_max = fmax(w_max, fabs(w[j]))

            if (
                w_max == 0.0
                or d_w_max / w_max <= d_w_tol
                or n_iter == max_iter - 1
                or n_active <= 1  # We have an analytical exact solution.
            ):
                # The biggest coordinate update of this iteration was smaller than the
                # tolerance: check the duality gap as ultimate stopping criterion.
                # We want to stop in case the gap is small enough but not exactly 0
                # only because of floating point arithmetic, and therefore set
                # gap_smaller_eps=True.
                gap, dual_norm_XtA = gap_enet(
                    n_samples, n_features, w, alpha, beta, X, y, R, XtA, positive,
                    gap_smaller_eps=True,
                )
                if gap <= tol:
                    # return if we reached desired tolerance
                    break

                # Gap Safe Screening Rules, see https://arxiv.org/abs/1802.07481, Eq. 11
                if do_screening:
                    n_active = 0
                    for j in range(n_features):
                        if excluded_set[j]:
                            continue
                        Xj_theta = XtA[j] / fmax(alpha, dual_norm_XtA)  # X @ dual_theta
                        d_j = (1 - fabs(Xj_theta)) / sqrt(norm2_cols_X[j] + beta)
                        if d_j <= sqrt(2 * gap) / alpha:
                            # include feature j
                            active_set[n_active] = j
                            excluded_set[j] = 0
                            n_active += 1
                        else:
                            if w[j] != 0:
                                # R += w[j] * X[:,j]
                                _axpy(n_samples, w[j], &X[0, j], 1, &R[0], 1)
                                w[j] = 0
                            excluded_set[j] = 1

        else:
            # for/else, runs if for doesn't end with a `break`
            with gil:
                message = (
                    message_conv +
                    f" Duality gap: {gap:.6e}, tolerance: {tol:.3e}"
                )
                if alpha < np.finfo(np.float64).eps:
                    message += "\n" + message_ridge
                warnings.warn(message, ConvergenceWarning)

    return np.asarray(w), gap, tol, n_iter + 1


def R_and_X_colnorm2_sparse(
    const floating[::1] w,
    const floating[::1] X_data,
    const int32_t[::1] X_indices,
    const int32_t[::1] X_indptr,
    const floating[::1] y,
    const floating[::1] sample_weight,
    const floating[::1] X_mean,
):
    """Compute residuals and squared column norms of X.

    Z = X - X_mean
    sw = sample_weight

    Parameters
    ----------
    w : memoryview of shape (n_features,)
        Coefficients.

    X_data, X_indices, X_indptr : memoryviews
        X in CSC format.

    y : memoryview of shape (n_samples,)
        Target values.

    sample_weight : memoryview of shape (n_samples,) or None
        Sample weights; None means unweighted.

    X_mean : memoryview of shape (n_features,)
        Column means of X used for centering.

    Returns
    -------
    R : memoryview of shape (n_samples,)
        Residuals:
        - unweighted: R = y - Z @ w
        - weighted:   R = sw * (y - Z @ w)

    norm2_cols_X : memoryview of shape (n_features,)
        Column norms of X:
        - unweighted: norm2_cols_X = np.sum((X - X_mean)**2, axis=0)
        - weighted:   norm2_cols_X = np.sum(sw * (X - X_mean)**2, axis=0)
    """
    cdef unsigned int n_samples = y.shape[0]
    cdef unsigned int n_features = w.shape[0]
    cdef floating tmp
    cdef floating w_j
    cdef floating X_mean_j
    cdef floating normalize_sum
    cdef floating sw_sum
    cdef int32_t i, i_ind
    cdef unsigned int j
    cdef int32_t startptr = X_indptr[0]
    cdef int32_t endptr
    cdef bint center = False
    cdef bint no_sample_weights = sample_weight is None

    cdef floating[::1] R = np.empty_like(y)
    cdef floating[::1] norm2_cols_X = np.empty_like(w)

    if X_mean is not None:
        # center = (X_mean != 0).any()
        for j in range(n_features):
            if X_mean[j]:
                center = True
                break
        if center and not no_sample_weights:
            sw_sum = np.sum(sample_weight)

    _copy(n_samples, &y[0], 1, &R[0], 1)
    if not no_sample_weights:
        for i in range(n_samples):
            R[i] *= sample_weight[i]

    for j in range(n_features):
        endptr = X_indptr[j + 1]
        normalize_sum = 0.0
        w_j = w[j]
        X_mean_j = X_mean[j]

        if no_sample_weights:
            for i_ind in range(startptr, endptr):
                i = X_indices[i_ind]
                normalize_sum += (X_data[i_ind] - X_mean_j) ** 2
                R[i] -= X_data[i_ind] * w_j
            norm2_cols_X[j] = normalize_sum
            if center:
                norm2_cols_X[j] += (n_samples - endptr + startptr) * X_mean_j ** 2
                for i in range(n_samples):
                    R[i] += X_mean_j * w_j
        else:
            # R = sw * (y - np.dot(X, w))
            for i_ind in range(startptr, endptr):
                i = X_indices[i_ind]
                tmp = sample_weight[i]
                # second term will be subtracted by loop over range(n_samples)
                normalize_sum += (
                    tmp * (X_data[i_ind] - X_mean_j) ** 2 - tmp * X_mean_j ** 2
                )
                R[i] -= tmp * X_data[i_ind] * w_j
            if center:
                normalize_sum += sw_sum * X_mean_j ** 2
                for i in range(n_samples):
                    R[i] += sample_weight[i] * X_mean_j * w_j
            norm2_cols_X[j] = normalize_sum
        startptr = endptr

    return R, norm2_cols_X


cdef inline void R_plus_wj_Xj(
    unsigned int n_samples,
    floating[::1] R,  # out
    const floating[::1] X_data,
    const int32_t[::1] X_indices,
    const int32_t[::1] X_indptr,
    const floating[::1] X_mean,
    bint center,
    const floating[::1] sample_weight,
    bint no_sample_weights,
    floating w_j,
    unsigned int j,
) noexcept nogil:
    """R += w_j * X[:,j]"""
    cdef int32_t i, i_ind
    cdef int32_t startptr = X_indptr[j]
    cdef int32_t endptr = X_indptr[j + 1]
    cdef floating sw
    cdef floating X_mean_j = X_mean[j]
    if no_sample_weights:
        for i_ind in range(startptr, endptr):
            i = X_indices[i_ind]
            R[i] += X_data[i_ind] * w_j
        if center:
            for i in range(n_samples):
                R[i] -= X_mean_j * w_j
    else:
        for i_ind in range(startptr, endptr):
            i = X_indices[i_ind]
            sw = sample_weight[i]
            R[i] += sw * X_data[i_ind] * w_j
        if center:
            for i in range(n_samples):
                R[i] -= sample_weight[i] * X_mean_j * w_j


cdef (floating, floating) gap_enet_sparse(
    int n_samples,
    int n_features,
    const floating[::1] w,
    floating alpha,  # L1 penalty
    floating beta,  # L2 penalty
    const floating[::1] X_data,
    const int32_t[::1] X_indices,
    const int32_t[::1] X_indptr,
    const floating[::1] y,
    const floating[::1] sample_weight,
    bint no_sample_weights,
    const floating[::1] X_mean,
    bint center,
    const floating[::1] R,  # current residuals = y - X @ w
    floating R_sum,
    floating[::1] XtA,  # XtA = X.T @ R - beta * w is calculated inplace
    bint positive,
    bint gap_smaller_eps,
) noexcept nogil:
    """Compute dual gap for use in enet_coordinate_descent_sparse.

    alpha > 0:            formulation A of the duality gap
    alpha = 0 & beta > 0: formulation B of the duality gap
    alpha = beta = 0:     OLS first order condition (=gradient)
    """
    cdef floating gap, primal, dual
    cdef floating dual_norm_XtA
    cdef floating R_norm2
    cdef floating Ry
    cdef floating w_l1_norm
    cdef floating w_l2_norm2 = 0.0
    cdef int32_t i, i_ind, j

    if floating is float:
        eps = FLT_EPSILON
    else:
        eps = DBL_EPSILON

    # w_l2_norm2 = w @ w
    if beta > 0:
        w_l2_norm2 = _dot(n_features, &w[0], 1, &w[0], 1)
    # R_norm2 = R @ R
    if no_sample_weights:
        R_norm2 = _dot(n_samples, &R[0], 1, &R[0], 1)
    else:
        R_norm2 = 0.0
        for i in range(n_samples):
            # R is already multiplied by sample_weight
            if sample_weight[i] != 0:
                R_norm2 += (R[i] ** 2) / sample_weight[i]
    # Ry = R @ y
    if not (alpha == 0 and beta == 0):
        # Note that with sample_weight, R equals R*sw and y is just y, such that
        # Ry = (sw * R) @ y, as it should be.
        Ry = _dot(n_samples, &R[0], 1, &y[0], 1)

    if alpha == 0:
        # XtA = X.T @ R
        for j in range(n_features):
            XtA[j] = 0.0
            for i_ind in range(X_indptr[j], X_indptr[j + 1]):
                i = X_indices[i_ind]
                XtA[j] += X_data[i_ind] * R[i]

            if center:
                XtA[j] -= X_mean[j] * R_sum
        # ||X'R||_2^2
        dual_norm_XtA = _dot(n_features, &XtA[0], 1, &XtA[0], 1)
        if beta == 0:
            # This is OLS, no dual gap available. Resort to first order condition
            #     X'R = 0
            #     gap = ||X'R||_2^2
            # Compare with stopping criterion of LSQR.
            gap = dual_norm_XtA
            return gap, dual_norm_XtA
        # This is Ridge regression, we use formulation B for the dual gap.
        primal = 0.5 * (R_norm2 + beta * w_l2_norm2)
        dual = -0.5 * R_norm2 + Ry - 1 / (2 * beta) * dual_norm_XtA
        gap = primal - dual
        if gap_smaller_eps and abs(gap) <= 2 * eps * primal:
            gap = 0.0
        return gap, dual_norm_XtA

    # XtA = X.T @ R - beta * w
    # sparse X.T @ dense R
    for j in range(n_features):
        XtA[j] = 0.0
        for i_ind in range(X_indptr[j], X_indptr[j + 1]):
            i = X_indices[i_ind]
            XtA[j] += X_data[i_ind] * R[i]

        if center:
            XtA[j] -= X_mean[j] * R_sum
        XtA[j] -= beta * w[j]

    # dual_norm_XtA
    if positive:
        dual_norm_XtA = max(n_features, &XtA[0])
    else:
        dual_norm_XtA = abs_max(n_features, &XtA[0])

    # w_l1_norm = np.sum(np.abs(w))
    w_l1_norm = _asum(n_features, &w[0], 1)

    gap = dual_gap_formulation_A(
        alpha=alpha,
        beta=beta,
        w_l1_norm=w_l1_norm,
        w_l2_norm2=w_l2_norm2,
        R_norm2=R_norm2,
        Ry=Ry,
        dual_norm_XtA=dual_norm_XtA,
        gap_smaller_eps=gap_smaller_eps,
    )
    return gap, dual_norm_XtA


def enet_coordinate_descent_sparse(
    floating[::1] w,
    floating alpha,
    floating beta,
    const floating[::1] X_data,
    const int32_t[::1] X_indices,
    const int32_t[::1] X_indptr,
    const floating[::1] y,
    const floating[::1] sample_weight,
    const floating[::1] X_mean,
    unsigned int max_iter,
    floating tol,
    object rng,
    bint random=0,
    bint positive=0,
    bint do_screening=1,
    bint early_stopping=1,
    floating[::1] R=None,
    floating[::1] norm2_cols_X=None,
):
    """Cython version of the coordinate descent algorithm for Elastic-Net

    We minimize:

        1/2 * norm(y - Z w, 2)^2 + alpha * norm(w, 1) + (beta/2) * norm(w, 2)^2

    where Z = X - X_mean.
    With sample weights sw, this becomes

        1/2 * sum(sw * (y - Z w)^2, axis=0) + alpha * norm(w, 1)
        + (beta/2) * norm(w, 2)^2

    and X_mean is the weighted average of X (per column).

    The rest is the same as enet_coordinate_descent, but for sparse X.

    Further Parameters
    ------------------
    random : bint, default=0 (False)
        If False, uses cyclic coordinate descent. If True, pick features at random.
    positive : bint, default=0 (False)
        If set to True, forces coefficients w to be positive.
    do_screening : bint, default=1 (True)
        If set to True, use gap safe screening rules to screen coefficients
        (exclude early based on dual gap).
    early_stopping : bint, default=1 (True)
        If set to True, check for convergence (with the dual gap) before entering the
        main iteration loop.
    R : memoryview or ndarray of shape (n_samples,) or None, default=None
        Initial value of the residual `R = y - X @ w`. If None, it will be computed.
        See `R_and_X_colnorm2_sparse` for how sample_weight and X_mean are taken
        into account.
    norm2_cols_X : memoryview or ndarray of shape (n_features,) or None, default=None
        Squared column norms of X. When R is None, R and norm2_cols_X are both computed
        and a given value is ignored; when R is given, norm2_cols_X must be given too.

    Returns
    -------
    w : ndarray of shape (n_features,)
        ElasticNet coefficients.
    gap : float
        Achieved dual gap.
    tol : float
        Equals input `tol` times `np.dot(y, y)`. The tolerance used for the dual gap.
    n_iter : int
        Number of coordinate descent iterations.
    """
    # Notes for sample_weight:
    # For dense X, one centers X and y and then rescales them by sqrt(sample_weight).
    # Here, for sparse X, we get the sample_weight averaged center X_mean. We take care
    # that every calculation results as if we had rescaled y and X (and therefore also
    # X_mean) by sqrt(sample_weight) without actually calculating the square root.
    # We work with:
    #     yw = sample_weight * y
    #     R = sample_weight * residual
    #     norm2_cols_X = np.sum(sample_weight * (X - X_mean)**2, axis=0)

    if floating is float:
        dtype = np.float32
    else:
        dtype = np.float64

    # get the data information into easy vars
    cdef unsigned int n_samples = y.shape[0]
    cdef unsigned int n_features = w.shape[0]

    cdef floating[::1] XtA = np.empty(n_features, dtype=dtype)
    cdef const floating[::1] yw

    cdef floating d_j
    cdef floating Xj_theta
    cdef floating tmp
    cdef floating w_j
    cdef floating d_w_max
    cdef floating w_max
    cdef floating d_w_j
    cdef floating gap = tol + 1.0
    cdef floating d_w_tol = tol
    cdef floating dual_norm_XtA
    cdef floating X_mean_j
    cdef floating R_sum = 0.0
    cdef unsigned int n_active = n_features
    cdef uint32_t[::1] active_set
    # TODO: use binset instead of array of bools
    cdef uint8_t[::1] excluded_set
    cdef int32_t i, i_ind
    cdef unsigned int j
    cdef unsigned int n_iter = 0
    cdef unsigned int f_iter
    cdef int32_t startptr = X_indptr[0]
    cdef int32_t endptr
    cdef uint32_t rand_r_state_seed = rng.randint(0, RAND_R_MAX)
    cdef uint32_t* rand_r_state = &rand_r_state_seed
    cdef bint center = False
    cdef bint no_sample_weights = sample_weight is None

    if alpha == 0:
        # No screeing without L1-penalty.
        do_screening = False

    if do_screening:
        active_set = np.empty(n_features, dtype=np.uint32)  # map [:n_active] -> j
        excluded_set = np.empty(n_features, dtype=np.uint8)

    if no_sample_weights:
        yw = y
    else:
        yw = np.multiply(sample_weight, y)

    # center = (X_mean != 0).any()
    if X_mean is not None:
        for j in range(n_features):
            if X_mean[j]:
                center = True
                break

    if R is None:
        # Initial value of the residuals. Will be kept up to date in the iterations.
        R, norm2_cols_X = R_and_X_colnorm2_sparse(
            w=w,
            X_data=X_data,
            X_indices=X_indices,
            X_indptr=X_indptr,
            y=y,
            sample_weight=sample_weight,
            X_mean=X_mean,
        )
    R_sum = np.sum(R)
    # Note: No need to update R_sum from here on because the update terms cancel each
    # other: w_j * np.sum(X[:,j] - X_mean[j]) = 0. R_sum is only used when X_mean is
    # provided.

    with nogil:

        # tol *= np.dot(y, y)
        # with sample weights: tol *= y @ (sw * y)
        tol *= _dot(n_samples, &y[0], 1, &yw[0], 1)

        # Check convergence before entering the main loop.
        # We want to avoid stopping too early and set gap_smaller_eps=False.
        gap, dual_norm_XtA = gap_enet_sparse(
            n_samples,
            n_features,
            w,
            alpha,
            beta,
            X_data,
            X_indices,
            X_indptr,
            y,
            sample_weight,
            no_sample_weights,
            X_mean,
            center,
            R,
            R_sum,
            XtA,
            positive,
            gap_smaller_eps=False,
        )
        if early_stopping and gap <= tol:
            with gil:
                return np.asarray(w), gap, tol, 0

        # Gap Safe Screening Rules, see https://arxiv.org/abs/1802.07481, Eq. 11
        if do_screening:
            n_active = 0
            for j in range(n_features):
                if norm2_cols_X[j] == 0:
                    w[j] = 0
                    excluded_set[j] = 1
                    continue
                Xj_theta = XtA[j] / fmax(alpha, dual_norm_XtA)  # X[:,j] @ dual_theta
                d_j = (1 - fabs(Xj_theta)) / sqrt(norm2_cols_X[j] + beta)
                if d_j <= sqrt(2 * gap) / alpha:
                    # include feature j
                    active_set[n_active] = j
                    excluded_set[j] = 0
                    n_active += 1
                else:
                    if w[j] != 0:
                        # R += w[j] * X[:,j]
                        R_plus_wj_Xj(
                            n_samples,
                            R,
                            X_data,
                            X_indices,
                            X_indptr,
                            X_mean,
                            center,
                            sample_weight,
                            no_sample_weights,
                            w[j],
                            j,
                        )
                        w[j] = 0
                    excluded_set[j] = 1

        for n_iter in range(max_iter):
            w_max = 0.0
            d_w_max = 0.0
            for f_iter in range(n_active):  # Loop over coordinates
                if random:
                    j = rand_int(n_active, rand_r_state)
                else:
                    j = f_iter

                if do_screening:
                    j = active_set[j]

                if norm2_cols_X[j] == 0.0:
                    continue

                startptr = X_indptr[j]
                endptr = X_indptr[j + 1]
                w_j = w[j]  # Store previous value
                X_mean_j = X_mean[j]

                # tmp = X[:,j] @ (R + w_j * X[:,j])
                tmp = 0.0
                for i_ind in range(startptr, endptr):
                    i = X_indices[i_ind]
                    tmp += R[i] * X_data[i_ind]
                tmp += w_j * norm2_cols_X[j]

                if center:
                    tmp -= R_sum * X_mean_j

                if positive and tmp < 0.0:
                    w[j] = 0.0
                else:
                    w[j] = fsign(tmp) * fmax(fabs(tmp) - alpha, 0) \
                            / (norm2_cols_X[j] + beta)

                if w[j] != w_j:
                    # R -=  (w[j] - w_j) * X[:,j] # Update residual
                    R_plus_wj_Xj(
                        n_samples,
                        R,
                        X_data,
                        X_indices,
                        X_indptr,
                        X_mean,
                        center,
                        sample_weight,
                        no_sample_weights,
                        w_j - w[j],
                        j,
                    )

                # update the maximum absolute coefficient update
                d_w_j = fabs(w[j] - w_j)
                d_w_max = fmax(d_w_max, d_w_j)

                w_max = fmax(w_max, fabs(w[j]))

            if (
                w_max == 0.0
                or d_w_max / w_max <= d_w_tol
                or n_iter == max_iter - 1
                or n_active <= 1  # We have an analytical exact solution.
            ):
                # The biggest coordinate update of this iteration was smaller than the
                # tolerance: check the duality gap as ultimate stopping criterion.
                # We want to stop in case the gap is small enough but not exactly 0
                # only because of floating point arithmetic, and therefore set
                # gap_smaller_eps=True.
                gap, dual_norm_XtA = gap_enet_sparse(
                    n_samples,
                    n_features,
                    w,
                    alpha,
                    beta,
                    X_data,
                    X_indices,
                    X_indptr,
                    y,
                    sample_weight,
                    no_sample_weights,
                    X_mean,
                    center,
                    R,
                    R_sum,
                    XtA,
                    positive,
                    gap_smaller_eps=True,
                )

                if gap <= tol:
                    # return if we reached desired tolerance
                    break

                # Gap Safe Screening Rules, see https://arxiv.org/abs/1802.07481, Eq. 11
                if do_screening:
                    n_active = 0
                    for j in range(n_features):
                        if excluded_set[j]:
                            continue
                        Xj_theta = XtA[j] / fmax(alpha, dual_norm_XtA)  # X @ dual_theta
                        d_j = (1 - fabs(Xj_theta)) / sqrt(norm2_cols_X[j] + beta)
                        if d_j <= sqrt(2 * gap) / alpha:
                            # include feature j
                            active_set[n_active] = j
                            excluded_set[j] = 0
                            n_active += 1
                        else:
                            if w[j] != 0:
                                # R += w[j] * X[:,j]
                                R_plus_wj_Xj(
                                    n_samples,
                                    R,
                                    X_data,
                                    X_indices,
                                    X_indptr,
                                    X_mean,
                                    center,
                                    sample_weight,
                                    no_sample_weights,
                                    w[j],
                                    j,
                                )
                                w[j] = 0
                            excluded_set[j] = 1

        else:
            # for/else, runs if for doesn't end with a `break`
            with gil:
                message = (
                    message_conv +
                    f" Duality gap: {gap:.6e}, tolerance: {tol:.3e}"
                )
                if alpha < np.finfo(np.float64).eps:
                    message += "\n" + message_ridge
                warnings.warn(message, ConvergenceWarning)

    return np.asarray(w), gap, tol, n_iter + 1


cdef (floating, floating) gap_enet_gram(
    int n_features,
    const floating[::1] w,
    floating alpha,  # L1 penalty
    floating beta,  # L2 penalty
    const floating[::1] Qw,
    const floating[::1] q,
    const floating y_norm2,
    floating[::1] XtA,  # XtA = X.T @ R - beta * w is calculated inplace
    bint positive,
    bint gap_smaller_eps,
) noexcept nogil:
    """Compute dual gap for use in enet_coordinate_descent.

    alpha > 0:            formulation A of the duality gap
    alpha = 0 & beta > 0: formulation B of the duality gap
    alpha = beta = 0:     OLS first order condition (=gradient)
    """
    cdef floating gap, primal, dual
    cdef floating dual_norm_XtA
    cdef floating R_norm2
    cdef floating Ry
    cdef floating w_l1_norm
    cdef floating w_l2_norm2 = 0.0
    cdef floating q_dot_w
    cdef floating wQw
    cdef unsigned int j

    if floating is float:
        eps = FLT_EPSILON
    else:
        eps = DBL_EPSILON

    # w_l2_norm2 = w @ w
    if beta > 0:
        w_l2_norm2 = _dot(n_features, &w[0], 1, &w[0], 1)
    # q_dot_w = w @ q
    q_dot_w = _dot(n_features, &w[0], 1, &q[0], 1)
    # wQw = w @ Q @ w
    wQw = _dot(n_features, &w[0], 1, &Qw[0], 1)
    # R_norm2 = R @ R, residual R = y - Xw
    R_norm2 = y_norm2 + wQw - 2.0 * q_dot_w
    # Ry = R @ y
    if not (alpha == 0 and beta == 0):
        # Note that R'y = (y - Xw)' y = ||y||_2^2 - w'X'y = y_norm2 - q_dot_w
        Ry = y_norm2 - q_dot_w

    if alpha == 0:
        # XtA = X'R
        for j in range(n_features):
            XtA[j] = q[j] - Qw[j]
        # ||X'R||_2^2
        dual_norm_XtA = _dot(n_features, &XtA[0], 1, &XtA[0], 1)
        if beta == 0:
            # This is OLS, no dual gap available. Resort to first order condition
            #     X'R = 0
            #     gap = ||X'R||_2^2
            # Compare with stopping criterion of LSQR.
            gap = dual_norm_XtA
            return gap, dual_norm_XtA
        # This is Ridge regression, we use formulation B for the dual gap.
        primal = 0.5 * (R_norm2 + beta * w_l2_norm2)
        dual = -0.5 * R_norm2 + Ry - 1 / (2 * beta) * dual_norm_XtA
        gap = primal - dual
        if gap_smaller_eps and abs(gap) <= 2 * eps * primal:
            gap = 0.0
        return gap, dual_norm_XtA

    # XtA = X.T @ R - beta * w = X.T @ y - X.T @ X @ w - beta * w
    for j in range(n_features):
        XtA[j] = q[j] - Qw[j] - beta * w[j]

    # dual_norm_XtA
    if positive:
        dual_norm_XtA = max(n_features, &XtA[0])
    else:
        dual_norm_XtA = abs_max(n_features, &XtA[0])

    # w_l1_norm = np.sum(np.abs(w))
    w_l1_norm = _asum(n_features, &w[0], 1)

    gap = dual_gap_formulation_A(
        alpha=alpha,
        beta=beta,
        w_l1_norm=w_l1_norm,
        w_l2_norm2=w_l2_norm2,
        R_norm2=R_norm2,
        Ry=Ry,
        dual_norm_XtA=dual_norm_XtA,
        gap_smaller_eps=gap_smaller_eps,
    )
    return gap, dual_norm_XtA


def enet_coordinate_descent_gram(
    floating[::1] w,
    floating alpha,
    floating beta,
    const floating[:, ::1] Q,
    const floating[::1] q,
    const floating[:] y,
    unsigned int max_iter,
    floating tol,
    object rng,
    bint random=0,
    bint positive=0,
    bint do_screening=1,
    bint early_stopping=1,
    floating[::1] Qw=None,
):
    """Cython version of the coordinate descent algorithm
        for Elastic-Net regression

        We minimize

        (1/2) * w^T Q w - q^T w + alpha norm(w, 1) + (beta/2) * norm(w, 2)^2
        +1/2 * y^T y

        which amount to the Elastic-Net problem when:
        Q = X^T X (Gram matrix)
        q = X^T y

    Further Parameters
    ------------------
    random : bint, default=0 (False)
        If False, uses cyclic coordinate descent. If True, pick features at random.
    positive : bint, default=0 (False)
        If set to True, forces coefficients w to be positive.
    do_screening : bint, default=1 (True)
        If set to True, use gap safe screening rules to screen coefficients
        (exclude early based on dual gap).
    early_stopping : bint, default=1 (True)
        If set to True, check for convergence (with the dual gap) before entering the
        main iteration loop.
    Qw : memoryview or ndarray of shape (n_features,) or None, default=None
        Initial value of `Q @ w`. If None, it will be computed.

    Returns
    -------
    w : ndarray of shape (n_features,)
        ElasticNet coefficients.
    gap : float
        Achieved dual gap.
    tol : float
        Equals input `tol` times `np.dot(y, y)`. The tolerance used for the dual gap.
    n_iter : int
        Number of coordinate descent iterations.
    """

    if floating is float:
        dtype = np.float32
    else:
        dtype = np.float64

    # get the data information into easy vars
    cdef unsigned int n_features = Q.shape[0]

    cdef floating[::1] XtA = np.zeros(n_features, dtype=dtype)
    cdef floating y_norm2 = np.dot(y, y)

    cdef floating d_j
    cdef floating radius
    cdef floating Xj_theta
    cdef floating tmp
    cdef floating w_j
    cdef floating d_w_max
    cdef floating w_max
    cdef floating d_w_j
    cdef floating gap = tol + 1.0
    cdef floating d_w_tol = tol
    cdef floating dual_norm_XtA
    cdef unsigned int n_active = n_features
    cdef uint32_t[::1] active_set
    # TODO: use binset instead of array of bools
    cdef uint8_t[::1] excluded_set
    cdef unsigned int j
    cdef unsigned int n_iter = 0
    cdef unsigned int f_iter
    cdef uint32_t rand_r_state_seed = rng.randint(0, RAND_R_MAX)
    cdef uint32_t* rand_r_state = &rand_r_state_seed

    if alpha == 0:
        # No screeing without L1-penalty.
        do_screening = False

    if do_screening:
        active_set = np.empty(n_features, dtype=np.uint32)  # map [:n_active] -> j
        excluded_set = np.empty(n_features, dtype=np.uint8)

    if Qw is None:
        # Initial value of Qw. Will be kept up to date in the iterations.
        Qw = np.dot(Q, w)

    with nogil:
        tol *= y_norm2

        # Check convergence before entering the main loop.
        # We want to avoid stopping too early and set gap_smaller_eps=False.
        gap, dual_norm_XtA = gap_enet_gram(
            n_features, w, alpha, beta, Qw, q, y_norm2, XtA, positive,
            gap_smaller_eps=False,
        )
        if early_stopping and 0 <= gap <= tol:
            # Only if gap >=0 as singular Q may cause dubious values of gap.
            with gil:
                return np.asarray(w), gap, tol, 0

        # Gap Safe Screening Rules, see https://arxiv.org/abs/1802.07481, Eq. 11
        if do_screening:
            # Due to floating point issues, gap might be negative.
            radius = sqrt(2 * fabs(gap)) / alpha
            n_active = 0
            for j in range(n_features):
                if Q[j, j] == 0:
                    w[j] = 0
                    excluded_set[j] = 1
                    continue
                Xj_theta = XtA[j] / fmax(alpha, dual_norm_XtA)  # X[:,j] @ dual_theta
                d_j = (1 - fabs(Xj_theta)) / sqrt(Q[j, j] + beta)
                if d_j <= radius:
                    # include feature j
                    active_set[n_active] = j
                    excluded_set[j] = 0
                    n_active += 1
                else:
                    if w[j] != 0:
                        # Qw -= w[j] * Q[j]  # Update Qw = Q @ w
                        _axpy(n_features, -w[j], &Q[j, 0], 1, &Qw[0], 1)
                        w[j] = 0
                    excluded_set[j] = 1

        for n_iter in range(max_iter):
            w_max = 0.0
            d_w_max = 0.0
            for f_iter in range(n_active):  # Loop over coordinates
                if random:
                    j = rand_int(n_active, rand_r_state)
                else:
                    j = f_iter

                if do_screening:
                    j = active_set[j]

                if Q[j, j] == 0.0:
                    continue

                w_j = w[j]  # Store previous value

                # if Q = X.T @ X then tmp = X[:,j] @ (y - X @ w + X[:, j] * w_j)
                tmp = q[j] - Qw[j] + w_j * Q[j, j]

                if positive and tmp < 0:
                    w[j] = 0.0
                else:
                    w[j] = fsign(tmp) * fmax(fabs(tmp) - alpha, 0) \
                        / (Q[j, j] + beta)

                if w[j] != w_j:
                    # Qw += (w[j] - w_j) * Q[j]  # Update Qw = Q @ w
                    _axpy(n_features, w[j] - w_j, &Q[j, 0], 1, &Qw[0], 1)

                # update the maximum absolute coefficient update
                d_w_j = fabs(w[j] - w_j)
                if d_w_j > d_w_max:
                    d_w_max = d_w_j

                if fabs(w[j]) > w_max:
                    w_max = fabs(w[j])

            if (
                w_max == 0.0
                or d_w_max / w_max <= d_w_tol
                or n_iter == max_iter - 1
                or n_active <= 1  # We have an analytical exact solution.
            ):
                # The biggest coordinate update of this iteration was smaller than the
                # tolerance: check the duality gap as ultimate stopping criterion.
                # We want to stop in case the gap is small enough but not exactly 0
                # only because of floating point arithmetic, and therefore set
                # gap_smaller_eps=True.
                gap, dual_norm_XtA = gap_enet_gram(
                    n_features, w, alpha, beta, Qw, q, y_norm2, XtA, positive,
                    gap_smaller_eps=True,
                )

                if gap <= tol:
                    # return if we reached desired tolerance
                    break

                # Gap Safe Screening Rules, see https://arxiv.org/abs/1802.07481, Eq. 11
                if do_screening:
                    # Due to floating point issues, gap might be negative.
                    radius = sqrt(2 * fabs(gap)) / alpha
                    n_active = 0
                    for j in range(n_features):
                        if excluded_set[j]:
                            continue
                        Xj_theta = XtA[j] / fmax(alpha, dual_norm_XtA)  # X @ dual_theta
                        d_j = (1 - fabs(Xj_theta)) / sqrt(Q[j, j] + beta)
                        if d_j <= radius:
                            # include feature j
                            active_set[n_active] = j
                            excluded_set[j] = 0
                            n_active += 1
                        else:
                            if w[j] != 0:
                                # Qw -= w[j] * Q[j]  # Update Qw = Q @ w
                                _axpy(n_features, -w[j], &Q[j, 0], 1, &Qw[0], 1)
                                w[j] = 0
                            excluded_set[j] = 1

        else:
            # for/else, runs if for doesn't end with a `break`
            with gil:
                message = (
                    message_conv +
                    f" Duality gap: {gap:.6e}, tolerance: {tol:.3e}"
                )
                if alpha < np.finfo(np.float64).eps:
                    message += "\n" + message_ridge
                warnings.warn(message, ConvergenceWarning)

    return np.asarray(w), gap, tol, n_iter + 1


def R_and_X_colnorm2_multi_task(
    const floating[::1, :] W,
    const floating[::1, :] X,
    bint X_is_sparse,
    const floating[::1] X_data,
    const int32_t[::1] X_indices,
    const int32_t[::1] X_indptr,
    const floating[::1, :] Y,
    const floating[::1] sample_weight,
    const floating[::1] X_mean,
):
    """Compute residuals and squared column norms of X.

    Z = X - X_mean
    sw = sample_weight

    Parameters
    ----------
    W : memoryview of shape (n_tasks, n_features)
        Coefficients.

    X : memoryview of shape (n_samples, n_features), Fortran-contiguous
        Training data, used when X_is_sparse is False.

    X_is_sparse : bool
        Whether X is given in CSC format by X_data, X_indices and X_indptr.

    X_data, X_indices, X_indptr : memoryviews
        X in CSC format, used when X_is_sparse is True.

    Y : memoryview of shape (n_samples, n_tasks)
        Target values.

    sample_weight : memoryview of shape (n_samples,) or None
        Sample weights; None means unweighted.

    X_mean : memoryview of shape (n_features,)
        Column means of X used for centering.

    Returns
    -------
    R : memoryview of shape (n_samples, n_tasks)
        Residuals:
        - unweighted: R = Y - Z @ W.T
        - weighted:   R = sw * (Y - Z @ W.T)

    norm2_cols_X : memoryview of shape (n_features,)
        Column norms of X:
        - unweighted: norm2_cols_X = np.sum((X - X_mean)**2, axis=0)
        - weighted:   norm2_cols_X = np.sum(sw * (X - X_mean)**2, axis=0)
    """
    if floating is float:
        dtype = np.float32
    else:
        dtype = np.float64
    cdef unsigned int n_samples = Y.shape[0]
    cdef unsigned int n_features = W.shape[1]
    cdef unsigned int n_tasks = Y.shape[1]
    cdef floating X_mean_j
    cdef floating normalize_sum
    cdef floating sw_sum
    cdef int32_t i, i_ind
    cdef unsigned int j
    cdef int32_t startptr
    cdef int32_t endptr
    cdef bint center = False
    cdef bint no_sample_weights = sample_weight is None

    cdef floating[::1, :] R = np.empty_like(Y, order="F")  # shape (n_samples, n_tasks)
    norm2_cols_X_array = np.empty(shape=n_features, dtype=dtype)
    cdef floating[::1] norm2_cols_X = norm2_cols_X_array

    if X_is_sparse and X_mean is not None:
        # center = (X_mean != 0).any()
        for j in range(n_features):
            if X_mean[j]:
                center = True
                break
        if center and not no_sample_weights:
            sw_sum = np.sum(sample_weight)

    if not X_is_sparse:
        np.einsum("ij,ij->j", X, X, dtype=dtype, out=norm2_cols_X_array)
    else:
        for j in range(n_features):
            startptr = X_indptr[j]
            endptr = X_indptr[j + 1]
            normalize_sum = 0.0
            X_mean_j = X_mean[j]

            if no_sample_weights:
                for i_ind in range(startptr, endptr):
                    normalize_sum += (X_data[i_ind] - X_mean_j) ** 2
                if center:
                    normalize_sum += (n_samples - endptr + startptr) * X_mean_j ** 2
            else:
                for i_ind in range(startptr, endptr):
                    i = X_indices[i_ind]
                    normalize_sum += sample_weight[i] * (
                        (X_data[i_ind] - X_mean_j) ** 2 - X_mean_j ** 2
                    )
                if center:
                    normalize_sum += sw_sum * X_mean_j ** 2
            norm2_cols_X[j] = normalize_sum

    _copy(n_samples * n_tasks, &Y[0, 0], 1, &R[0, 0], 1)
    if not no_sample_weights and X_is_sparse:
        for t in range(n_tasks):
            for i in range(n_samples):
                R[i, t] *= sample_weight[i]
    for j in range(n_features):
        for t in range(n_tasks):
            if W[t, j] != 0:
                if not X_is_sparse:
                    _axpy(n_samples, -W[t, j], &X[0, j], 1, &R[0, t], 1)
                else:
                    if no_sample_weights:
                        sparse_axpy(j, -W[t, j], X_data, X_indices, X_indptr, R[:, t])
                    else:
                        startptr = X_indptr[j]
                        endptr = X_indptr[j + 1]
                        for i_ind in range(startptr, endptr):
                            i = X_indices[i_ind]
                            R[i, t] -= sample_weight[i] * X_data[i_ind] * W[t, j]

        if X_is_sparse and center:
            # R = Y - (X - X_mean) @ W.T
            X_mean_j = X_mean[j]
            if no_sample_weights:
                for i in range(n_samples):
                    for t in range(n_tasks):
                        R[i, t] += X_mean_j * W[t, j]
            else:
                for i in range(n_samples):
                    for t in range(n_tasks):
                        R[i, t] += sample_weight[i] * X_mean_j * W[t, j]

    return R, norm2_cols_X


cdef (floating, floating) gap_enet_multi_task(
    int n_samples,
    int n_features,
    int n_tasks,
    const floating[::1, :] W,
    floating alpha,
    floating beta,
    const floating[::1, :] X,
    bint X_is_sparse,
    const floating[::1] X_data,
    const int32_t[::1] X_indices,
    const int32_t[::1] X_indptr,
    const floating[::1, :] Y,
    const floating[::1] sample_weight,
    bint no_sample_weights,
    const floating[::1] X_mean,
    bint center,
    const floating[::1, :] R,  # current residuals = y - X @ W.T
    const floating[::1] R_sum,
    floating[:, ::1] XtA,  # out
    floating[::1] XtA_row_norms,  # out
    bint gap_smaller_eps,
) noexcept nogil:
    """Compute dual gap for use in enet_coordinate_descent_multi_task.

    Parameters
    ----------
    W : memoryview of shape (n_tasks, n_features)
    X : memoryview of shape (n_samples, n_features)
    Y : memoryview of shape (n_samples, n_tasks)
    R : memoryview of shape (n_samples, n_tasks)
        Current residuals = Y - X @ W.T
    XtA : memoryview of shape (n_features, n_tasks)
        Inplace calculated as XtA = X.T @ R - beta * W.T
    XtA_row_norms : memoryview of shape n_features
        Inplace calculated as np.sqrt(np.sum(XtA ** 2, axis=1))
    """
    cdef floating gap, primal, dual
    cdef floating dual_norm_XtA
    cdef floating R_norm2
    cdef floating Ry
    cdef floating w_l21_norm
    cdef floating w_l2_norm2 = 0.0
    cdef unsigned int t, j
    cdef int32_t i

    if floating is float:
        eps = FLT_EPSILON
    else:
        eps = DBL_EPSILON

    # w_l2_norm2 = linalg.norm(W, ord="fro") ** 2
    if beta > 0:
        w_l2_norm2 = _dot(n_features * n_tasks, &W[0, 0], 1, &W[0, 0], 1)
    # R_norm2 = linalg.norm(R, ord="fro") ** 2
    if not X_is_sparse or no_sample_weights:
        R_norm2 = _dot(n_samples * n_tasks, &R[0, 0], 1, &R[0, 0], 1)
    else:  # sparse X and sample_weights
        R_norm2 = 0.0
        for t in range(n_tasks):
            for i in range(n_samples):
                # R is already multiplied by sample_weight
                if sample_weight[i] != 0:
                    R_norm2 += (R[i, t] ** 2) / sample_weight[i]
    # Ry = np.sum(R * Y)
    if not (alpha == 0 and beta == 0):
        # Note that with sample_weight, R equals R*sw and y is just y, such that
        # Ry = (sw * R) @ y, as it should be.
        Ry = _dot(n_samples * n_tasks, &R[0, 0], 1, &Y[0, 0], 1)

    if alpha == 0:
        # XtA = X.T @ R
        for j in range(n_features):
            for t in range(n_tasks):
                if not X_is_sparse:
                    XtA[j, t] = _dot(n_samples, &X[0, j], 1, &R[0, t], 1)
                else:
                    XtA[j, t] = sparse_dot(j, X_data, X_indices, X_indptr, R[:, t])
                    if center:
                        XtA[j, t] -= X_mean[j] * R_sum[t]
        # ||X'R||_2^2
        dual_norm_XtA = _dot(n_features * n_tasks, &XtA[0, 0], 1, &XtA[0, 0], 1)
        if beta == 0:
            # This is OLS, no dual gap available. Resort to first order condition
            #     X'R = 0
            #     gap = ||X'R||_2^2
            # Compare with stopping criterion of LSQR.
            gap = dual_norm_XtA
            return gap, dual_norm_XtA
        # This is Ridge regression, we use formulation B for the dual gap.
        primal = 0.5 * (R_norm2 + beta * w_l2_norm2)
        dual = -0.5 * R_norm2 + Ry - 1 / (2 * beta) * dual_norm_XtA
        gap = primal - dual
        if gap_smaller_eps and abs(gap) <= 2 * eps * primal:
            gap = 0.0
        return gap, dual_norm_XtA

    # XtA = X.T @ R - beta * W.T
    for j in range(n_features):
        for t in range(n_tasks):
            if not X_is_sparse:
                XtA[j, t] = _dot(n_samples, &X[0, j], 1, &R[0, t], 1) - beta * W[t, j]
            else:
                XtA[j, t] = sparse_dot(j, X_data, X_indices, X_indptr, R[:, t])
                if center:
                    XtA[j, t] -= X_mean[j] * R_sum[t]
                XtA[j, t] -= beta * W[t, j]

    # dual_norm_XtA = np.max(np.sqrt(np.sum(XtA ** 2, axis=1)))
    dual_norm_XtA = 0.0
    for j in range(n_features):
        # np.sqrt(np.sum(XtA ** 2, axis=1))
        XtA_row_norms[j] = _nrm2(n_tasks, &XtA[j, 0], 1)
        if XtA_row_norms[j] > dual_norm_XtA:
            dual_norm_XtA = XtA_row_norms[j]

    # w_l21_norm = np.sqrt(np.sum(W ** 2, axis=0)).sum()
    w_l21_norm = 0.0
    for ii in range(n_features):
        w_l21_norm += _nrm2(n_tasks, &W[0, ii], 1)

    gap = dual_gap_formulation_A(
        alpha=alpha,
        beta=beta,
        w_l1_norm=w_l21_norm,
        w_l2_norm2=w_l2_norm2,
        R_norm2=R_norm2,
        Ry=Ry,
        dual_norm_XtA=dual_norm_XtA,
        gap_smaller_eps=gap_smaller_eps,
    )
    return gap, dual_norm_XtA


def enet_coordinate_descent_multi_task(
    floating[::1, :] W,
    floating alpha,
    floating beta,
    const floating[::1, :] X,
    bint X_is_sparse,
    const floating[::1] X_data,
    const int32_t[::1] X_indices,
    const int32_t[::1] X_indptr,
    const floating[::1, :] Y,
    const floating[::1] sample_weight,
    const floating[::1] X_mean,
    unsigned int max_iter,
    floating tol,
    object rng,
    bint random=0,
    bint do_screening=1,
    bint early_stopping=1,
    floating[::1, :] R=None,
    floating[::1] norm2_cols_X=None,
):
    """Cython version of the coordinate descent algorithm
        for Elastic-Net multi-task regression

        We minimize

        0.5 * norm(Y - X W.T, 2)^2 + alpha * ||W.T||_21 + 0.5 * beta * norm(W.T, 2)^2

    The algorithm follows
    Noah Simon, Jerome Friedman, Trevor Hastie. 2013.
    A Blockwise Descent Algorithm for Group-penalized Multiresponse and Multinomial
    Regression
    https://doi.org/10.48550/arXiv.1311.6529

    Further Parameters
    ------------------
    random : bint, default=0 (False)
        If False, uses cyclic coordinate descent. If True, pick features at random.
    do_screening : bint, default=1 (True)
        If set to True, use gap safe screening rules to screen coefficients
        (exclude early based on dual gap).
    early_stopping : bint, default=1 (True)
        If set to True, check for convergence (with the dual gap) before entering the
        main iteration loop.
    R : memoryview or ndarray of shape (n_samples, n_tasks) or None, default=None
        Initial value of the residual `R = y - X @ W.T`. If None, it will be computed.
        See `R_and_X_colnorm2_multi_task` for how sample_weight and X_mean are taken
        into account.
    norm2_cols_X : memoryview or ndarray of shape (n_features,) or None, default=None
        Squared column norms of X. When R is None, R and norm2_cols_X are both computed
        and a given value is ignored; when R is given, norm2_cols_X must be given too.

    Returns
    -------
    W : ndarray of shape (n_tasks, n_features)
        ElasticNet coefficients.
    gap : float
        Achieved dual gap.
    tol : float
        Equals input `tol` times `np.dot(y, y)`. The tolerance used for the dual gap.
    n_iter : int
        Number of coordinate descent iterations.
    """
    # Notes for sample_weight:
    # For dense X, one centers X and y and then rescales them by sqrt(sample_weight).
    # For sparse X, we get the sample_weight averaged center X_mean. We take care
    # that every calculation results as if we had rescaled y and X (and therefore also
    # X_mean) by sqrt(sample_weight) without actually calculating the square root.
    # We work with:
    #     yw = sample_weight * y
    #     R = sample_weight * residual
    #     norm2_cols_X = np.sum(sample_weight * (X - X_mean)**2, axis=0)

    if floating is float:
        dtype = np.float32
    else:
        dtype = np.float64

    # get the data information into easy vars
    cdef unsigned int n_samples = Y.shape[0]
    cdef unsigned int n_features = W.shape[1]
    cdef unsigned int n_tasks = Y.shape[1]

    cdef floating[:, ::1] XtA = np.empty((n_features, n_tasks), dtype=dtype)
    cdef floating[::1] XtA_row_norms = np.empty(n_features, dtype=dtype)
    cdef const floating[::1, :] Yw

    cdef floating d_j
    cdef floating Xj_theta
    cdef floating[::1] tmp = np.empty(n_tasks, dtype=dtype)
    cdef floating[::1] w_j = np.empty(n_tasks, dtype=dtype)
    cdef floating d_w_max
    cdef floating w_max
    cdef floating d_w_j
    cdef floating nn
    cdef floating W_j_abs_max
    cdef floating gap = tol + 1.0
    cdef floating d_w_tol = tol
    cdef floating dual_norm_XtA
    cdef floating[::1] R_sum
    cdef unsigned int n_active = n_features
    cdef uint32_t[::1] active_set
    # TODO: use binset instead of array of bools
    cdef uint8_t[::1] excluded_set
    cdef unsigned int j
    cdef unsigned int t
    cdef unsigned int n_iter = 0
    cdef unsigned int f_iter
    cdef uint32_t rand_r_state_seed = rng.randint(0, RAND_R_MAX)
    cdef uint32_t* rand_r_state = &rand_r_state_seed
    cdef bint center = False
    cdef bint no_sample_weights = sample_weight is None

    if alpha == 0:
        # No screeing without L1-penalty.
        do_screening = False

    if do_screening:
        active_set = np.empty(n_features, dtype=np.uint32)  # map [:n_active] -> j
        excluded_set = np.empty(n_features, dtype=np.uint8)

    if no_sample_weights or not X_is_sparse:
        Yw = Y
    else:
        Yw = np.multiply(sample_weight[:, None], Y)

    if R is None:
        # Initial value of the residuals. Will be kept up to date in the iterations.
        R, norm2_cols_X = R_and_X_colnorm2_multi_task(
            W=W,
            X=X,
            X_is_sparse=X_is_sparse,
            X_data=X_data,
            X_indices=X_indices,
            X_indptr=X_indptr,
            Y=Y,
            sample_weight=sample_weight,
            X_mean=X_mean,
        )

    if X_is_sparse and X_mean is not None:
        # center = (X_mean != 0).any()
        for j in range(n_features):
            if X_mean[j]:
                center = True
                break

        R_sum = np.sum(R, axis=0)
    # Note: No need to update R_sum from here on because the update terms cancel each
    # other: w_j[t] * np.sum(X[:,j] - X_mean[j]) = 0. R_sum is only ever needed and
    # calculated if X_mean is provided.

    with nogil:

        # tol = tol * linalg.norm(Y, ord='fro') ** 2
        # with sample weights: tol *= y @ (sw * y)
        tol *= _dot(n_samples * n_tasks, &Y[0, 0], 1, &Yw[0, 0], 1)

        # Check convergence before entering the main loop.
        # We want to avoid stopping too early and set gap_smaller_eps=False.
        gap, dual_norm_XtA = gap_enet_multi_task(
            n_samples=n_samples,
            n_features=n_features,
            n_tasks=n_tasks,
            W=W,
            alpha=alpha,
            beta=beta,
            X=X,
            X_is_sparse=X_is_sparse,
            X_data=X_data,
            X_indices=X_indices,
            X_indptr=X_indptr,
            Y=Y,
            sample_weight=sample_weight,
            no_sample_weights=no_sample_weights,
            X_mean=X_mean,
            center=center,
            R=R,
            R_sum=R_sum,
            XtA=XtA,
            XtA_row_norms=XtA_row_norms,
            gap_smaller_eps=False,
        )
        if early_stopping and gap <= tol:
            with gil:
                return np.asarray(W), gap, tol, 0

        # Gap Safe Screening Rules for multi-task Lasso, see
        # https://arxiv.org/abs/1703.07285 Eq 2.2. (also arxiv:1506.03736)
        if do_screening:
            n_active = 0
            for j in range(n_features):
                if norm2_cols_X[j] == 0:
                    for t in range(n_tasks):
                        W[t, j] = 0
                    excluded_set[j] = 1
                    continue
                # Xj_theta = ||X[:,j] @ dual_theta||_2
                Xj_theta = XtA_row_norms[j] / fmax(alpha, dual_norm_XtA)
                d_j = (1 - Xj_theta) / sqrt(norm2_cols_X[j] + beta)
                if d_j <= sqrt(2 * gap) / alpha:
                    # include feature j
                    active_set[n_active] = j
                    excluded_set[j] = 0
                    n_active += 1
                else:
                    # R += W[:, j] * X[:, 1][:, None]
                    for t in range(n_tasks):
                        if W[t, j] != 0:
                            if not X_is_sparse:
                                _axpy(n_samples, W[t, j], &X[0, j], 1, &R[0, t], 1)
                            else:
                                R_plus_wj_Xj(
                                    n_samples=n_samples,
                                    R=R[:, t],
                                    X_data=X_data,
                                    X_indices=X_indices,
                                    X_indptr=X_indptr,
                                    X_mean=X_mean,
                                    center=center,
                                    sample_weight=sample_weight,
                                    no_sample_weights=no_sample_weights,
                                    w_j=W[t, j],
                                    j=j,
                                )
                            W[t, j] = 0
                    excluded_set[j] = 1

        for n_iter in range(max_iter):
            w_max = 0.0
            d_w_max = 0.0
            for f_iter in range(n_active):  # Loop over coordinates
                if random:
                    j = rand_int(n_active, rand_r_state)
                else:
                    j = f_iter

                if do_screening:
                    j = active_set[j]

                if norm2_cols_X[j] == 0.0:
                    continue

                # w_j = W[:, j] # Store previous value
                _copy(n_tasks, &W[0, j], 1, &w_j[0], 1)

                # tmp = X[:, j] @ (R + w_j * X[:,j][:, None])
                # first part: X[:, j] @ R
                #   Using BLAS Level 2:
                #   _gemv(RowMajor, Trans, n_samples, n_tasks, 1.0, &R[0, 0],
                #         n_tasks, &X[0, j], 1, 0.0, &tmp[0], 1)
                # second part: (X[:, j] @ X[:,j]) * w_j = norm2_cols * w_j
                #   Using BLAS Level 1:
                #   _axpy(n_tasks, norm2_cols[j], &w_j[0], 1, &tmp[0], 1)
                # Using BLAS Level 1 (faster for small vectors like here):
                for t in range(n_tasks):
                    if not X_is_sparse:
                        tmp[t] = _dot(n_samples, &X[0, j], 1, &R[0, t], 1)
                    else:
                        tmp[t] = sparse_dot(j, X_data, X_indices, X_indptr, R[:, t])
                    # As we have the loop already, we use it to replace the second BLAS
                    # Level 1, i.e., _axpy, too.
                    tmp[t] += w_j[t] * norm2_cols_X[j]

                # nn = sqrt(np.sum(tmp ** 2))
                nn = _nrm2(n_tasks, &tmp[0], 1)

                # W[:, j] = tmp * fmax(1. - alpha / nn, 0) / (norm2_cols_X[j] + beta)
                _copy(n_tasks, &tmp[0], 1, &W[0, j], 1)
                _scal(n_tasks, fmax(1. - alpha / nn, 0) / (norm2_cols_X[j] + beta),
                      &W[0, j], 1)

                # Update residual
                # Using numpy:
                #   R -= (W[:, j] - w_j) * X[:, j][:, None]
                # Using BLAS Level 1 and 2:
                #   _axpy(n_tasks, -1.0, &W[0, j], 1, &w_j[0], 1)
                #   _ger(RowMajor, n_samples, n_tasks, 1.0,
                #        &X[0, j], 1, &w_j, 1,
                #        &R[0, 0], n_tasks)
                # Using BLAS Level 1 (faster for small vectors like here):
                for t in range(n_tasks):
                    if W[t, j] != w_j[t]:
                        if not X_is_sparse:
                            _axpy(n_samples, w_j[t] - W[t, j], &X[0, j], 1, &R[0, t], 1)
                        else:
                            R_plus_wj_Xj(
                                n_samples=n_samples,
                                R=R[:, t],
                                X_data=X_data,
                                X_indices=X_indices,
                                X_indptr=X_indptr,
                                X_mean=X_mean,
                                center=center,
                                sample_weight=sample_weight,
                                no_sample_weights=no_sample_weights,
                                w_j=w_j[t] - W[t, j],
                                j=j,
                            )

                # update the maximum absolute coefficient update
                d_w_j = diff_abs_max(n_tasks, &W[0, j], &w_j[0])

                if d_w_j > d_w_max:
                    d_w_max = d_w_j

                W_j_abs_max = abs_max(n_tasks, &W[0, j])
                if W_j_abs_max > w_max:
                    w_max = W_j_abs_max

            if (
                w_max == 0.0
                or d_w_max / w_max <= d_w_tol
                or n_iter == max_iter - 1
                or n_active <= 1  # We have an analytical exact solution.
            ):
                # The biggest coordinate update of this iteration was smaller than the
                # tolerance: check the duality gap as ultimate stopping criterion.
                # We want to stop in case the gap is small enough but not exactly 0
                # only because of floating point arithmetic, and therefore set
                # gap_smaller_eps=True.
                gap, dual_norm_XtA = gap_enet_multi_task(
                    n_samples=n_samples,
                    n_features=n_features,
                    n_tasks=n_tasks,
                    W=W,
                    alpha=alpha,
                    beta=beta,
                    X=X,
                    X_is_sparse=X_is_sparse,
                    X_data=X_data,
                    X_indices=X_indices,
                    X_indptr=X_indptr,
                    Y=Y,
                    sample_weight=sample_weight,
                    no_sample_weights=no_sample_weights,
                    X_mean=X_mean,
                    center=center,
                    R=R,
                    R_sum=R_sum,
                    XtA=XtA,
                    XtA_row_norms=XtA_row_norms,
                    gap_smaller_eps=True,
                )
                if gap <= tol:
                    # return if we reached desired tolerance
                    break

                # Gap Safe Screening Rules for multi-task Lasso, see
                # https://arxiv.org/abs/1703.07285 Eq 2.2. (also arxiv:1506.03736)
                if do_screening:
                    n_active = 0
                    for j in range(n_features):
                        if excluded_set[j]:
                            continue
                        # Xj_theta = ||X[:,j] @ dual_theta||_2
                        Xj_theta = XtA_row_norms[j] / fmax(alpha, dual_norm_XtA)
                        d_j = (1 - Xj_theta) / sqrt(norm2_cols_X[j] + beta)
                        if d_j <= sqrt(2 * gap) / alpha:
                            # include feature j
                            active_set[n_active] = j
                            excluded_set[j] = 0
                            n_active += 1
                        else:
                            # R += W[:, j] * X[:, 1][:, None]
                            for t in range(n_tasks):
                                if W[t, j] != 0:
                                    if not X_is_sparse:
                                        _axpy(n_samples, W[t, j], &X[0, j], 1, &R[0, t], 1)
                                    else:
                                        R_plus_wj_Xj(
                                            n_samples=n_samples,
                                            R=R[:, t],
                                            X_data=X_data,
                                            X_indices=X_indices,
                                            X_indptr=X_indptr,
                                            X_mean=X_mean,
                                            center=center,
                                            sample_weight=sample_weight,
                                            no_sample_weights=no_sample_weights,
                                            w_j=W[t, j],
                                            j=j,
                                        )
                                    W[t, j] = 0
                            excluded_set[j] = 1

        else:
            # for/else, runs if for doesn't end with a `break`
            with gil:
                message = (
                    message_conv +
                    f" Duality gap: {gap:.6e}, tolerance: {tol:.3e}"
                )
                if alpha < np.finfo(np.float64).eps:
                    message += "\n" + message_ridge
                warnings.warn(message, ConvergenceWarning)

    return np.asarray(W), gap, tol, n_iter + 1


###############################################################################
# Regularization path solvers
#
# The functions below fit a whole regularization path in one call. They run the
# same coordinate descent iterations as the single alpha solvers above, alpha after
# alpha with warm starts, but compute everything that does not depend on alpha only
# once and keep the state that the coordinate updates maintain (residuals, their
# products with X, Q @ w) from one alpha to the next instead of recomputing it.


cdef int _warn_not_converged(floating alpha, floating gap, floating tol) except -1:
    """Emit the ConvergenceWarning of the single alpha solvers."""
    message = message_conv + f" Duality gap: {gap:.6e}, tolerance: {tol:.3e}"
    if alpha < np.finfo(np.float64).eps:
        message += "\n" + message_ridge
    warnings.warn(message, ConvergenceWarning)
    return 0


cdef void _sync_Qw(
    unsigned int n_features,
    const floating[:, ::1] Q,
    floating[::1] Qw,  # inout
    floating[::1] pending,  # inout
    uint32_t[::1] touched,
    uint8_t[::1] is_touched,  # inout
    unsigned int n_touched,
    const uint32_t[::1] active_set,
    unsigned int n_active,
    floating[::1] saved,  # work array of shape (n_features,)
) noexcept nogil:
    """Bring the entries of Qw outside of the active set up to date.

    During restricted epochs only Qw[active_set[:n_active]] is updated and the
    coefficient changes are accumulated in pending[touched[:n_touched]]. This adds
    Q[j] * pending[j] for every touched j to all of Qw while keeping the already up to
    date active entries, and resets pending and is_touched.
    """
    cdef unsigned int k, j
    for k in range(n_active):
        saved[k] = Qw[active_set[k]]
    for k in range(n_touched):
        j = touched[k]
        _axpy(n_features, pending[j], &Q[j, 0], 1, &Qw[0], 1)
        pending[j] = 0.0
        is_touched[j] = 0
    for k in range(n_active):
        Qw[active_set[k]] = saved[k]


cdef int _fill_Q_rows(
    object fill_rows,
    uint8_t[::1] Q_rows_ready,
    const floating[::1] XtA,
    const uint32_t[::1] needed,
    unsigned int n_needed,
) except -1:
    """Fill the rows of Q of the features needed[:n_needed] that are not filled yet.

    Q is computed on demand, by `fill_rows(rows)`. To keep the number of calls
    logarithmic in n_features, every call fills at least half as many rows as are
    already filled (and at least 8), completed by the features with the largest |XtA|
    (the next candidates to become nonzero).
    """
    cdef unsigned int k, j, n_missing = 0, n_ready = 0, n_extra
    cdef unsigned int n_features = Q_rows_ready.shape[0]
    missing = np.empty(n_needed, dtype=np.intp)
    cdef Py_ssize_t[::1] missing_view = missing
    for k in range(n_needed):
        j = needed[k]
        if not Q_rows_ready[j]:
            missing_view[n_missing] = j
            n_missing += 1
    if n_missing == 0:
        return 0
    for j in range(n_features):
        n_ready += Q_rows_ready[j]
    rows = missing[:n_missing]
    ready = np.asarray(Q_rows_ready)
    ready[rows] = 1
    # n_extra = min(max(n_ready // 2, 8) - n_missing, n_features - n_ready - n_missing)
    n_extra = n_ready // 2 if n_ready // 2 > 8 else 8
    n_extra = n_extra - n_missing if n_extra > n_missing else 0
    if n_extra > n_features - n_ready - n_missing:
        n_extra = n_features - n_ready - n_missing
    if n_extra > 0:
        candidates = np.flatnonzero(ready == 0)
        score = np.abs(np.asarray(XtA)[candidates])
        if n_extra < candidates.shape[0]:
            candidates = candidates[np.argpartition(-score, n_extra - 1)[:n_extra]]
        ready[candidates] = 1
        rows = np.concatenate((rows, candidates))
    fill_rows(rows)
    return 0


def enet_coordinate_descent_gram_path(
    floating[::1] w,
    const floating[::1] l1_regs,
    const floating[::1] l2_regs,
    const floating[:, ::1] Q,
    const floating[::1] Q_diag,
    const floating[::1] q,
    floating y_norm2,
    floating[::1] Qw,
    floating[:, :] coefs,
    floating[::1] gaps,
    int32_t[::1] n_iters,
    unsigned int max_iter,
    floating tol,
    object rng,
    bint random=0,
    bint positive=0,
    bint do_screening=1,
    bint early_stopping=1,
    bint gram_rules=1,
    object fill_rows=None,
):
    """Coordinate descent for Elastic-Net along a path, in terms of Q = X.T @ X.

    Fits, for every k, the problem of `enet_coordinate_descent_gram` with
    alpha = l1_regs[k] and beta = l2_regs[k], warm started at the solution of k - 1,
    with the same iterations, convergence checks and screening rules.

    Parameters
    ----------
    w : ndarray of shape (n_features,)
        Initial coefficients, holds the coefficients of the last alpha on exit.
    l1_regs, l2_regs : ndarray of shape (n_alphas,)
        L1 and L2 penalties alpha and beta of the path (already multiplied by
        n_samples).
    Q : ndarray of shape (n_features, n_features), C-ordered
        Gram matrix X.T @ X. When `fill_rows` is given, only the rows filled by it are
        read.
    Q_diag : ndarray of shape (n_features,)
        Diagonal of Q (the squared column norms of X).
    q : ndarray of shape (n_features,)
        X.T @ y.
    y_norm2 : float
        y @ y.
    Qw : ndarray of shape (n_features,)
        Q @ w for the initial w. It is kept up to date and holds Q @ w on exit.
    coefs : ndarray of shape (n_features, n_alphas)
        Output, coefficients at each alpha.
    gaps : ndarray of shape (n_alphas,)
        Output, dual gap at each alpha.
    n_iters : ndarray of shape (n_alphas,)
        Output, number of iterations at each alpha.
    gram_rules : bint, default=1 (True)
        If True, use the early stopping and screening radius rules of
        `enet_coordinate_descent_gram` (robust to a slightly negative gap of a
        singular Q). If False, use those of `enet_coordinate_descent` on dense X,
        which this solver then replaces for precompute=False.
    fill_rows : callable or None, default=None
        If None, Q is complete. Else Q is filled on demand: `fill_rows(rows)` must fill
        Q[rows] = X[:, rows].T @ X. A row is needed when its coefficient changes, so
        mostly only the rows of the features that become nonzero are filled.

    The other parameters are those of `enet_coordinate_descent_gram`.

    Returns
    -------
    tol : float
        Equals input `tol` times `y_norm2`. The tolerance used for the dual gap.
    """
    if floating is float:
        dtype = np.float32
    else:
        dtype = np.float64

    cdef unsigned int n_features = Q.shape[0]
    cdef unsigned int n_alphas = l1_regs.shape[0]
    cdef floating[::1] XtA = np.zeros(n_features, dtype=dtype)
    cdef floating[::1] pending = np.zeros(n_features, dtype=dtype)
    cdef floating[::1] saved = np.empty(n_features, dtype=dtype)
    cdef uint32_t[::1] touched = np.empty(n_features, dtype=np.uint32)
    cdef uint8_t[::1] is_touched = np.zeros(n_features, dtype=np.uint8)
    cdef uint32_t[::1] active_set = np.empty(n_features, dtype=np.uint32)
    cdef uint8_t[::1] excluded_set = np.zeros(n_features, dtype=np.uint8)
    cdef uint8_t[::1] Q_rows_ready
    cdef uint32_t[::1] needed = np.empty(1, dtype=np.uint32)
    cdef bint lazy = fill_rows is not None

    cdef floating alpha, beta
    cdef floating d_j
    cdef floating radius
    cdef floating Xj_theta
    cdef floating tmp
    cdef floating w_j
    cdef floating d_w
    cdef floating d_w_max
    cdef floating w_max
    cdef floating d_w_j
    cdef floating gap
    cdef floating d_w_tol = tol
    cdef floating tol_scaled = tol * y_norm2
    cdef floating dual_norm_XtA
    cdef unsigned int n_active
    cdef unsigned int n_touched = 0
    cdef unsigned int j, k, a
    cdef unsigned int n_iter
    cdef unsigned int f_iter
    cdef unsigned int i_alpha
    cdef uint32_t rand_r_state_seed
    cdef uint32_t* rand_r_state = &rand_r_state_seed
    cdef bint screening
    cdef bint restricted
    cdef bint converged

    if lazy:
        # Rows of the initially nonzero coefficients, as screening may set them to 0.
        Q_rows_ready = np.zeros(n_features, dtype=np.uint8)
        n_active = 0
        for j in range(n_features):
            if w[j] != 0:
                active_set[n_active] = j
                n_active += 1
        _fill_Q_rows(fill_rows, Q_rows_ready, XtA, active_set, n_active)

    for i_alpha in range(n_alphas):
        alpha = l1_regs[i_alpha]
        beta = l2_regs[i_alpha]
        rand_r_state_seed = rng.randint(0, RAND_R_MAX)
        screening = do_screening and alpha != 0
        converged = True
        restricted = False
        n_active = n_features

        with nogil:
            # Check convergence before entering the main loop.
            gap, dual_norm_XtA = gap_enet_gram(
                n_features, w, alpha, beta, Qw, q, y_norm2, XtA, positive,
                gap_smaller_eps=False,
            )
            if early_stopping and (
                (gram_rules and 0 <= gap <= tol_scaled)
                or (not gram_rules and gap <= tol_scaled)
            ):
                n_iter = 0
            else:
                n_iter = 1
        if n_iter == 0:
            coefs[:, i_alpha] = w
            gaps[i_alpha] = gap
            n_iters[i_alpha] = 0
            continue

        with nogil:
            # Gap Safe Screening Rules, see https://arxiv.org/abs/1802.07481, Eq. 11
            if screening:
                if gram_rules:
                    radius = sqrt(2 * fabs(gap)) / alpha
                else:
                    radius = sqrt(2 * gap) / alpha
                n_active = 0
                for j in range(n_features):
                    if Q_diag[j] == 0:
                        w[j] = 0
                        excluded_set[j] = 1
                        continue
                    Xj_theta = XtA[j] / fmax(alpha, dual_norm_XtA)
                    d_j = (1 - fabs(Xj_theta)) / sqrt(Q_diag[j] + beta)
                    if d_j <= radius:
                        active_set[n_active] = j
                        excluded_set[j] = 0
                        n_active += 1
                    else:
                        if w[j] != 0:
                            # Qw -= w[j] * Q[j]
                            _axpy(n_features, -w[j], &Q[j, 0], 1, &Qw[0], 1)
                            w[j] = 0
                        excluded_set[j] = 1
            else:
                for j in range(n_features):
                    active_set[j] = j

        with nogil:
            # With a small active set, only Q @ w restricted to the active set is needed
            # in the epochs; the other entries are brought up to date before each gap.
            restricted = screening and 2 * n_active < n_features
            n_iter = 0
            for n_iter in range(max_iter):
                w_max = 0.0
                d_w_max = 0.0
                for f_iter in range(n_active):  # Loop over coordinates
                    if random:
                        j = rand_int(n_active, rand_r_state)
                    else:
                        j = f_iter

                    if screening:
                        j = active_set[j]

                    if Q_diag[j] == 0.0:
                        continue

                    w_j = w[j]  # Store previous value

                    # if Q = X.T @ X then tmp = X[:,j] @ (y - X @ w + X[:, j] * w_j)
                    tmp = q[j] - Qw[j] + w_j * Q_diag[j]

                    if positive and tmp < 0:
                        w[j] = 0.0
                    else:
                        w[j] = fsign(tmp) * fmax(fabs(tmp) - alpha, 0) \
                            / (Q_diag[j] + beta)

                    if w[j] != w_j:
                        d_w = w[j] - w_j
                        if lazy and not Q_rows_ready[j]:
                            with gil:
                                needed[0] = j
                                _fill_Q_rows(fill_rows, Q_rows_ready, XtA, needed, 1)
                        if restricted:
                            # Qw[active] += d_w * Q[j, active]
                            for k in range(n_active):
                                a = active_set[k]
                                Qw[a] += d_w * Q[j, a]
                            pending[j] += d_w
                            if not is_touched[j]:
                                is_touched[j] = 1
                                touched[n_touched] = j
                                n_touched += 1
                        else:
                            # Qw += d_w * Q[j]
                            _axpy(n_features, d_w, &Q[j, 0], 1, &Qw[0], 1)

                    # update the maximum absolute coefficient update
                    d_w_j = fabs(w[j] - w_j)
                    if d_w_j > d_w_max:
                        d_w_max = d_w_j

                    if fabs(w[j]) > w_max:
                        w_max = fabs(w[j])

                if (
                    w_max == 0.0
                    or d_w_max / w_max <= d_w_tol
                    or n_iter == max_iter - 1
                    or n_active <= 1  # We have an analytical exact solution.
                ):
                    if n_touched:
                        _sync_Qw(n_features, Q, Qw, pending, touched, is_touched,
                                 n_touched, active_set, n_active, saved)
                        n_touched = 0
                    gap, dual_norm_XtA = gap_enet_gram(
                        n_features, w, alpha, beta, Qw, q, y_norm2, XtA, positive,
                        gap_smaller_eps=True,
                    )

                    if gap <= tol_scaled:
                        # return if we reached desired tolerance
                        break

                    # Gap Safe Screening Rules, see https://arxiv.org/abs/1802.07481
                    if screening:
                        if gram_rules:
                            radius = sqrt(2 * fabs(gap)) / alpha
                        else:
                            radius = sqrt(2 * gap) / alpha
                        n_active = 0
                        for j in range(n_features):
                            if excluded_set[j]:
                                continue
                            Xj_theta = XtA[j] / fmax(alpha, dual_norm_XtA)
                            d_j = (1 - fabs(Xj_theta)) / sqrt(Q_diag[j] + beta)
                            if d_j <= radius:
                                active_set[n_active] = j
                                excluded_set[j] = 0
                                n_active += 1
                            else:
                                if w[j] != 0:
                                    # Qw -= w[j] * Q[j]
                                    _axpy(n_features, -w[j], &Q[j, 0], 1, &Qw[0], 1)
                                    w[j] = 0
                                excluded_set[j] = 1
                        restricted = 2 * n_active < n_features
            else:
                converged = False
            if n_touched:
                _sync_Qw(n_features, Q, Qw, pending, touched, is_touched,
                         n_touched, active_set, n_active, saved)
                n_touched = 0

        coefs[:, i_alpha] = w
        gaps[i_alpha] = gap
        n_iters[i_alpha] = n_iter + 1
        if not converged:
            _warn_not_converged(alpha, gap, tol_scaled)

    return tol_scaled


cdef inline void _sparse_R_add(
    floating[::1] R,  # inout
    const floating[::1] X_data,
    const int32_t[::1] X_indices,
    const int32_t[::1] X_indptr,
    const floating[::1] sample_weight,
    bint no_sample_weights,
    floating w_j,
    unsigned int j,
) noexcept nogil:
    """R += w_j * sample_weight * X[:, j] on the nonzero entries of X[:, j] only."""
    cdef int32_t i, i_ind
    if no_sample_weights:
        for i_ind in range(X_indptr[j], X_indptr[j + 1]):
            R[X_indices[i_ind]] += X_data[i_ind] * w_j
    else:
        for i_ind in range(X_indptr[j], X_indptr[j + 1]):
            i = X_indices[i_ind]
            R[i] += sample_weight[i] * X_data[i_ind] * w_j


cdef inline void _flush_R_offset(
    unsigned int n_samples,
    floating[::1] R,  # inout
    const floating[::1] sample_weight,
    bint no_sample_weights,
    floating R_offset,
) noexcept nogil:
    """R += R_offset * sample_weight (or + R_offset without sample weights)."""
    cdef unsigned int i
    if no_sample_weights:
        for i in range(n_samples):
            R[i] += R_offset
    else:
        for i in range(n_samples):
            R[i] += sample_weight[i] * R_offset


cdef inline floating _sparse_dot_unrolled(
    int32_t j,
    const floating[::1] X_data,  # in
    const int32_t[::1] X_indices,  # in
    const int32_t[::1] X_indptr,  # in
    const floating[::1] y,
) noexcept nogil:
    """X[:, j] @ y for sparse CSC X, with 4 partial sums for instruction parallelism."""
    cdef int32_t i_ind
    cdef int32_t startptr = X_indptr[j]
    cdef int32_t endptr = X_indptr[j + 1]
    cdef int32_t end4 = startptr + ((endptr - startptr) // 4) * 4
    cdef floating s0 = 0.0, s1 = 0.0, s2 = 0.0, s3 = 0.0

    for i_ind in range(startptr, end4, 4):
        s0 += X_data[i_ind] * y[X_indices[i_ind]]
        s1 += X_data[i_ind + 1] * y[X_indices[i_ind + 1]]
        s2 += X_data[i_ind + 2] * y[X_indices[i_ind + 2]]
        s3 += X_data[i_ind + 3] * y[X_indices[i_ind + 3]]
    for i_ind in range(end4, endptr):
        s0 += X_data[i_ind] * y[X_indices[i_ind]]
    return (s0 + s1) + (s2 + s3)


cdef (floating, floating) gap_enet_sparse_lazy(
    unsigned int n_samples,
    unsigned int n_features,
    const floating[::1] w,
    floating alpha,  # L1 penalty
    floating beta,  # L2 penalty
    const floating[::1] X_data,
    const int32_t[::1] X_indices,
    const int32_t[::1] X_indptr,
    const floating[::1] y,
    const floating[::1] inv_sample_weight,
    bint no_sample_weights,
    const floating[::1] X_mean,
    bint center,
    const floating[::1] R,  # current residuals = sw * (y - Z @ w)
    floating R_sum,
    uint64_t R_version,  # changes whenever R changes
    floating[::1] XtR,  # inout, X.T @ R (X not centered) where up to date
    uint64_t[::1] XtR_version,  # inout, R_version of each entry of XtR
    floating[::1] XtA,  # out, XtA = Z.T @ R - beta * w, or an upper bound of |XtA|
    const uint32_t[::1] candidates,
    unsigned int n_candidates,
    bint full,
    floating[::1] R_ref,  # inout, residuals of the last full computation
    floating[::1] XtA_ref,  # inout, Z.T @ R_ref of the last full computation
    const floating[::1] X_col_norms,  # np.linalg.norm(X, axis=0)
    floating[::1] ZtR,  # out, Z.T @ R where computed exactly
    bint positive,
    bint gap_smaller_eps,
    bint* refresh,  # out, whether the next call should be a full one
    floating* R_l2_out,  # out, ||R||_2
    floating[::1] R_stats,  # inout, R_norm2, Ry, ||R||_2, ||R - R_ref||_2
    uint64_t* R_stats_version,  # inout, R_version of R_stats
) noexcept nogil:
    """Dual gap of gap_enet_sparse, computing X.T @ R only where it is needed.

    The dual gap only needs the maximum of XtA (of |XtA| if not positive). It is
    computed exactly for the candidates[:n_candidates] (all features with a nonzero
    coefficient must be among them). For the other features, which have w[j] = 0, the
    change of XtA[j] since the last full computation is bounded by
    ||X[:, j]|| * ||R - R_ref||, such that XtA[j] is only computed if this bound does
    not prove it smaller than the maximum. Then XtA[j] holds that bound on |XtA[j]|
    and XtR_version[j] != R_version. This yields the same gap as computing all of
    X.T @ R. With full=True, or for alpha = 0, all of X.T @ R is computed and R_ref,
    XtA_ref are updated. Where XtA[j] is computed exactly, ZtR[j] = XtA[j] + beta * w[j]
    is set too. The norms and products of R in R_stats are reused while R_version
    does not change.
    """
    cdef floating gap, primal, dual
    cdef floating dual_norm_XtA = 0.0
    cdef floating R_norm2
    cdef floating Ry = 0.0
    cdef floating w_l1_norm
    cdef floating w_l2_norm2 = 0.0
    cdef floating d_R2 = 0.0, R2, d_R_norm, R_l2
    cdef floating bound, tmp
    cdef unsigned int i, j, k
    cdef unsigned int n_extra = 0

    if floating is float:
        eps = FLT_EPSILON
    else:
        eps = DBL_EPSILON

    # w_l2_norm2 = w @ w
    if beta > 0:
        w_l2_norm2 = _dot(n_features, &w[0], 1, &w[0], 1)
    if R_stats_version[0] == R_version:
        R_norm2 = R_stats[0]
        Ry = R_stats[1]
        R_l2 = R_stats[2]
    else:
        # R_norm2 = R @ R, with sample weights R @ (R / sample_weight)
        if no_sample_weights:
            R_norm2 = _dot(n_samples, &R[0], 1, &R[0], 1)
        else:
            R_norm2 = 0.0
            for i in range(n_samples):
                # inv_sample_weight is 0 where sample_weight is 0
                R_norm2 += (R[i] ** 2) * inv_sample_weight[i]
        # Ry = R @ y
        Ry = _dot(n_samples, &R[0], 1, &y[0], 1)
        # R2 = ||R||_2 ** 2
        R2 = R_norm2 if no_sample_weights else _dot(n_samples, &R[0], 1, &R[0], 1)
        R_l2 = sqrt(R2)
        R_stats[0] = R_norm2
        R_stats[1] = Ry
        R_stats[2] = R_l2
        R_stats[3] = -1.0  # ||R - R_ref|| not computed yet
        R_stats_version[0] = R_version
    R_l2_out[0] = R_l2

    if full or alpha == 0:
        # XtA = Z.T @ R for all features
        for j in range(n_features):
            if XtR_version[j] != R_version:
                XtR[j] = _sparse_dot_unrolled(j, X_data, X_indices, X_indptr, R)
                XtR_version[j] = R_version
            XtA_ref[j] = XtR[j]
            if center:
                XtA_ref[j] -= X_mean[j] * R_sum
            ZtR[j] = XtA_ref[j]
        _copy(n_samples, &R[0], 1, &R_ref[0], 1)
        R_stats[3] = 0.0
        refresh[0] = False

        if alpha == 0:
            for j in range(n_features):
                XtA[j] = XtA_ref[j]
            dual_norm_XtA = _dot(n_features, &XtA[0], 1, &XtA[0], 1)
            if beta == 0:
                gap = dual_norm_XtA
                return gap, dual_norm_XtA
            primal = 0.5 * (R_norm2 + beta * w_l2_norm2)
            dual = -0.5 * R_norm2 + Ry - 1 / (2 * beta) * dual_norm_XtA
            gap = primal - dual
            if gap_smaller_eps and abs(gap) <= 2 * eps * primal:
                gap = 0.0
            return gap, dual_norm_XtA

        # XtA = Z.T @ R - beta * w
        for j in range(n_features):
            XtA[j] = XtA_ref[j] - beta * w[j]
        if positive:
            dual_norm_XtA = max(n_features, &XtA[0])
        else:
            dual_norm_XtA = abs_max(n_features, &XtA[0])
    else:
        # XtA = Z.T @ R - beta * w for the candidates
        dual_norm_XtA = -INFINITY if positive else 0.0
        for k in range(n_candidates):
            j = candidates[k]
            if XtR_version[j] != R_version:
                XtR[j] = _sparse_dot_unrolled(j, X_data, X_indices, X_indptr, R)
                XtR_version[j] = R_version
            ZtR[j] = XtR[j]
            if center:
                ZtR[j] -= X_mean[j] * R_sum
            XtA[j] = ZtR[j] - beta * w[j]
            tmp = XtA[j] if positive else fabs(XtA[j])
            if tmp > dual_norm_XtA:
                dual_norm_XtA = tmp

        if n_candidates < n_features:
            # ||R - R_ref||
            if R_stats[3] < 0:
                for i in range(n_samples):
                    d_R2 += (R[i] - R_ref[i]) ** 2
                R_stats[3] = sqrt(d_R2)
            d_R_norm = R_stats[3]
            for j in range(n_features):
                if XtR_version[j] != R_version:
                    # Upper bounds of XtA[j] and of |XtA[j]|, with a margin for the
                    # rounding errors of computing XtA[j].
                    tmp = X_col_norms[j] * (d_R_norm + 1e-12 * R_l2)
                    bound = (fabs(XtA_ref[j]) + tmp) * (1 + 1e-9)
                    if positive:
                        tmp = XtA_ref[j] + tmp + 1e-9 * bound
                    else:
                        tmp = bound
                    if tmp < dual_norm_XtA:
                        XtA[j] = bound
                        continue
                    XtR[j] = _sparse_dot_unrolled(j, X_data, X_indices, X_indptr, R)
                    XtR_version[j] = R_version
                    n_extra += 1
                ZtR[j] = XtR[j]
                if center:
                    ZtR[j] -= X_mean[j] * R_sum
                XtA[j] = ZtR[j] - beta * w[j]
                tmp = XtA[j] if positive else fabs(XtA[j])
                if tmp > dual_norm_XtA:
                    dual_norm_XtA = tmp
            # When the bounds got loose, start over from a full computation.
            refresh[0] = n_extra > 8 and 8 * n_extra > n_features - n_candidates

    w_l1_norm = _asum(n_features, &w[0], 1)

    gap = dual_gap_formulation_A(
        alpha=alpha,
        beta=beta,
        w_l1_norm=w_l1_norm,
        w_l2_norm2=w_l2_norm2,
        R_norm2=R_norm2,
        Ry=Ry,
        dual_norm_XtA=dual_norm_XtA,
        gap_smaller_eps=gap_smaller_eps,
    )
    return gap, dual_norm_XtA


def enet_coordinate_descent_sparse_path(
    floating[::1] w,
    const floating[::1] l1_regs,
    const floating[::1] l2_regs,
    const floating[::1] X_data,
    const int32_t[::1] X_indices,
    const int32_t[::1] X_indptr,
    const floating[::1] y,
    const floating[::1] sample_weight,
    const floating[::1] X_mean,
    floating[:, :] coefs,
    floating[::1] gaps,
    int32_t[::1] n_iters,
    unsigned int max_iter,
    floating tol,
    object rng,
    bint random=0,
    bint positive=0,
    bint do_screening=1,
    bint early_stopping=1,
):
    """Coordinate descent for Elastic-Net on sparse X along a path.

    Fits, for every k, the problem of `enet_coordinate_descent_sparse` with
    alpha = l1_regs[k] and beta = l2_regs[k], warm started at the solution of k - 1,
    with the same iterations, convergence checks and screening rules.

    Parameters
    ----------
    w : ndarray of shape (n_features,)
        Initial coefficients, holds the coefficients of the last alpha on exit.
    l1_regs, l2_regs : ndarray of shape (n_alphas,)
        L1 and L2 penalties alpha and beta of the path (already multiplied by
        n_samples).
    coefs : ndarray of shape (n_features, n_alphas)
        Output, coefficients at each alpha.
    gaps : ndarray of shape (n_alphas,)
        Output, dual gap at each alpha.
    n_iters : ndarray of shape (n_alphas,)
        Output, number of iterations at each alpha.

    The other parameters are those of `enet_coordinate_descent_sparse`.

    Returns
    -------
    tol : float
        Equals input `tol` times `y @ (sample_weight * y)`. The tolerance used for the
        dual gap.
    """
    # The weighted residuals R = sample_weight * (y - (X - X_mean) @ w) are dense even
    # for sparse X. To only visit the nonzero entries of X[:, j] in a coordinate
    # update, the centering part sample_weight * X_mean[j] * (w_j_new - w_j_old) of the
    # updates is summed up in the scalar R_offset: the residuals are
    # R + sample_weight * R_offset. Then
    #     X[:, j] @ (R + sample_weight * R_offset) = X[:, j] @ R + R_offset * X_sw_sum[j]
    # with X_sw_sum = np.sum(sample_weight * X, axis=0). R_offset is added to R (and
    # reset to 0) before each dual gap and at the end of each alpha.
    # The dual gaps only compute X.T @ R where needed, see gap_enet_sparse_lazy:
    # entries of XtR = X.T @ R (X not centered) are kept, also from one alpha to the
    # next, as long as R does not change, which R_version tracks.
    if floating is float:
        dtype = np.float32
    else:
        dtype = np.float64

    cdef unsigned int n_samples = y.shape[0]
    cdef unsigned int n_features = w.shape[0]
    cdef unsigned int n_alphas = l1_regs.shape[0]
    cdef bint no_sample_weights = sample_weight is None
    cdef floating[::1] norm2_cols_X = np.empty(n_features, dtype=dtype)
    cdef floating[::1] X_sw_sum = np.empty(n_features, dtype=dtype)
    cdef floating[::1] R
    cdef floating[::1] XtR = np.empty(n_features, dtype=dtype)
    cdef floating[::1] XtA = np.empty(n_features, dtype=dtype)
    cdef uint64_t[::1] XtR_version = np.zeros(n_features, dtype=np.ulonglong)
    cdef floating[::1] R_ref = np.empty(n_samples, dtype=dtype)
    cdef floating[::1] XtA_ref = np.empty(n_features, dtype=dtype)
    cdef floating[::1] X_col_norms = np.empty(n_features, dtype=dtype)
    cdef floating[::1] ZtR = np.empty(n_features, dtype=dtype)
    cdef floating[::1] update_norms = np.empty(n_features, dtype=dtype)
    cdef floating[::1] R_stats = np.empty(4, dtype=dtype)
    cdef uint64_t R_stats_version = 0
    cdef floating[::1] inv_sample_weight = None
    cdef uint32_t[::1] active_set = np.empty(n_features, dtype=np.uint32)
    cdef uint8_t[::1] excluded_set = np.zeros(n_features, dtype=np.uint8)

    cdef floating alpha, beta
    cdef floating d_j
    cdef floating Xj_theta
    cdef floating tmp
    cdef floating w_j
    cdef floating d_w_max
    cdef floating w_max
    cdef floating d_w_j
    cdef floating gap
    cdef floating d_w_tol = tol
    cdef floating tol_scaled
    cdef floating dual_norm_XtA
    cdef floating X_mean_j
    cdef floating sw
    cdef floating sw_sum = 0.0
    cdef floating normalize_sum
    cdef floating X_sw_sum_j
    cdef floating X_col_norm2_j
    cdef floating update_norm2_j
    cdef floating sw2_sum = 0.0
    cdef floating radius
    cdef floating R_l2 = 0.0
    cdef floating d_R_bound = 0.0
    cdef floating R_sum = 0.0
    cdef floating R_offset = 0.0
    cdef unsigned int n_active
    cdef int32_t i, i_ind, startptr, endptr
    cdef unsigned int j
    cdef unsigned int n_iter
    cdef unsigned int f_iter
    cdef unsigned int i_alpha
    cdef uint32_t rand_r_state_seed
    cdef uint32_t* rand_r_state = &rand_r_state_seed
    cdef bint center = False
    cdef bint screening
    cdef bint converged
    cdef uint64_t R_version = 1
    cdef bint full_gap = True

    if no_sample_weights:
        R = np.array(y, dtype=dtype)
    else:
        R = np.multiply(sample_weight, y)
        inv_sample_weight = np.zeros(n_samples, dtype=dtype)

    with nogil:
        # center = (X_mean != 0).any()
        for j in range(n_features):
            if X_mean[j]:
                center = True
                break

        if no_sample_weights:
            sw_sum = n_samples
        else:
            for i in range(n_samples):
                sw_sum += sample_weight[i]
                sw2_sum += sample_weight[i] ** 2
                if sample_weight[i] != 0:
                    inv_sample_weight[i] = 1 / sample_weight[i]

        # tol *= np.dot(y, y), with sample weights tol *= y @ (sw * y)
        tol_scaled = tol * _dot(n_samples, &y[0], 1, &R[0], 1)

        # norm2_cols_X = np.sum(sw * (X - X_mean)**2, axis=0)
        # X_sw_sum = np.sum(sw * X, axis=0)
        for j in range(n_features):
            X_mean_j = X_mean[j]
            startptr = X_indptr[j]
            endptr = X_indptr[j + 1]
            normalize_sum = 0.0
            X_sw_sum_j = 0.0
            X_col_norm2_j = 0.0
            for i_ind in range(startptr, endptr):
                X_col_norm2_j += X_data[i_ind] ** 2
            X_col_norms[j] = sqrt(X_col_norm2_j)
            if no_sample_weights:
                for i_ind in range(startptr, endptr):
                    normalize_sum += (X_data[i_ind] - X_mean_j) ** 2
                    X_sw_sum_j += X_data[i_ind]
                if center:
                    normalize_sum += (n_samples - endptr + startptr) * X_mean_j ** 2
            else:
                update_norm2_j = 0.0
                for i_ind in range(startptr, endptr):
                    i = X_indices[i_ind]
                    sw = sample_weight[i]
                    normalize_sum += (sw * (X_data[i_ind] - X_mean_j) ** 2
                                      - sw * X_mean_j ** 2)
                    X_sw_sum_j += sw * X_data[i_ind]
                    update_norm2_j += sw ** 2 * (
                        (X_data[i_ind] - X_mean_j) ** 2 - X_mean_j ** 2
                    )
                if center:
                    normalize_sum += sw_sum * X_mean_j ** 2
                    update_norm2_j += sw2_sum * X_mean_j ** 2
            norm2_cols_X[j] = normalize_sum
            X_sw_sum[j] = X_sw_sum_j
            # ||sw * (X[:, j] - X_mean[j])||, the change of R per unit change of w[j]
            if no_sample_weights:
                update_norms[j] = sqrt(fmax(normalize_sum, 0.0))
            else:
                update_norms[j] = sqrt(fmax(update_norm2_j, 0.0))

            # R = sw * (y - X @ w), the centering part goes to R_offset
            if w[j] != 0:
                _sparse_R_add(R, X_data, X_indices, X_indptr, sample_weight,
                              no_sample_weights, -w[j], j)
                R_offset += X_mean_j * w[j]

        if center:
            _flush_R_offset(n_samples, R, sample_weight, no_sample_weights, R_offset)
            # R_sum = np.sum(R). It does not change in the coordinate updates, as
            # w_j * np.sum(sw * (X[:, j] - X_mean[j])) = 0.
            for i in range(n_samples):
                R_sum += R[i]
        R_offset = 0.0

        # All features are the candidates of the first dual gap (a full one).
        n_active = n_features
        for j in range(n_features):
            active_set[j] = j

    for i_alpha in range(n_alphas):
        alpha = l1_regs[i_alpha]
        beta = l2_regs[i_alpha]
        rand_r_state_seed = rng.randint(0, RAND_R_MAX)
        screening = do_screening and alpha != 0
        converged = True

        with nogil:
            # Check convergence before entering the main loop. The candidates are the
            # features not excluded at the previous alpha, which include all nonzero
            # coefficients.
            gap, dual_norm_XtA = gap_enet_sparse_lazy(
                n_samples, n_features, w, alpha, beta, X_data, X_indices, X_indptr,
                y, inv_sample_weight, no_sample_weights, X_mean, center, R, R_sum,
                R_version, XtR, XtR_version, XtA, active_set, n_active, full_gap,
                R_ref, XtA_ref, X_col_norms, ZtR, positive, False, &full_gap, &R_l2,
                R_stats, &R_stats_version,
            )
            d_R_bound = 0.0
            if early_stopping and gap <= tol_scaled:
                n_iter = 0
            else:
                n_iter = 1
        if n_iter == 0:
            coefs[:, i_alpha] = w
            gaps[i_alpha] = gap
            n_iters[i_alpha] = 0
            continue

        with nogil:
            # Gap Safe Screening Rules, see https://arxiv.org/abs/1802.07481, Eq. 11
            if screening:
                radius = sqrt(2 * gap) / alpha
                n_active = 0
                for j in range(n_features):
                    if norm2_cols_X[j] == 0:
                        w[j] = 0
                        excluded_set[j] = 1
                        continue
                    Xj_theta = XtA[j] / fmax(alpha, dual_norm_XtA)
                    d_j = (1 - fabs(Xj_theta)) / sqrt(norm2_cols_X[j] + beta)
                    if XtR_version[j] != R_version:
                        # XtA[j] is an upper bound of |XtA[j]| (and w[j] = 0), such
                        # that d_j is a lower bound.
                        if d_j > radius:
                            excluded_set[j] = 1
                            continue
                        XtR[j] = _sparse_dot_unrolled(j, X_data, X_indices, X_indptr, R)
                        XtR_version[j] = R_version
                        ZtR[j] = XtR[j]
                        if center:
                            ZtR[j] -= X_mean[j] * R_sum
                        XtA[j] = ZtR[j] - beta * w[j]
                        Xj_theta = XtA[j] / fmax(alpha, dual_norm_XtA)
                        d_j = (1 - fabs(Xj_theta)) / sqrt(norm2_cols_X[j] + beta)
                    if d_j <= radius:
                        active_set[n_active] = j
                        excluded_set[j] = 0
                        n_active += 1
                    else:
                        if w[j] != 0:
                            # R += w[j] * X[:,j]
                            _sparse_R_add(R, X_data, X_indices, X_indptr,
                                          sample_weight, no_sample_weights, w[j], j)
                            R_offset -= w[j] * X_mean[j]
                            R_version += 1
                            d_R_bound += fabs(w[j]) * update_norms[j]
                            w[j] = 0
                        excluded_set[j] = 1

            n_iter = 0
            for n_iter in range(max_iter):
                w_max = 0.0
                d_w_max = 0.0
                for f_iter in range(n_active):  # Loop over coordinates
                    if random:
                        j = rand_int(n_active, rand_r_state)
                    else:
                        j = f_iter

                    if screening:
                        j = active_set[j]

                    if norm2_cols_X[j] == 0.0:
                        continue

                    w_j = w[j]  # Store previous value
                    if w_j == 0:
                        # Since the last dual gap, |X[:, j] @ R| changed by at most
                        # ||X[:, j]|| * ||R_now - R_gap|| <= ||X[:, j]|| * d_R_bound.
                        # If that proves |tmp| <= alpha (tmp <= alpha if positive), w[j]
                        # stays 0 and this update can be skipped.
                        tmp = X_col_norms[j] * (d_R_bound + 1e-12 * R_l2)
                        if positive:
                            tmp += ZtR[j] + 1e-9 * (fabs(ZtR[j]) + tmp)
                        else:
                            tmp = (fabs(ZtR[j]) + tmp) * (1 + 1e-9)
                        if tmp < alpha:
                            continue
                    X_mean_j = X_mean[j]

                    # tmp = X[:,j] @ (R + w_j * X[:,j])
                    tmp = _sparse_dot_unrolled(j, X_data, X_indices, X_indptr, R)
                    if center:
                        tmp += R_offset * X_sw_sum[j]
                    tmp += w_j * norm2_cols_X[j]

                    if center:
                        tmp -= R_sum * X_mean_j

                    if positive and tmp < 0.0:
                        w[j] = 0.0
                    else:
                        w[j] = fsign(tmp) * fmax(fabs(tmp) - alpha, 0) \
                                / (norm2_cols_X[j] + beta)

                    if w[j] != w_j:
                        # R -=  (w[j] - w_j) * X[:,j] # Update residual
                        _sparse_R_add(R, X_data, X_indices, X_indptr, sample_weight,
                                      no_sample_weights, w_j - w[j], j)
                        R_offset -= (w_j - w[j]) * X_mean_j
                        R_version += 1
                        d_R_bound += fabs(w_j - w[j]) * update_norms[j]

                    # update the maximum absolute coefficient update
                    d_w_j = fabs(w[j] - w_j)
                    d_w_max = fmax(d_w_max, d_w_j)

                    w_max = fmax(w_max, fabs(w[j]))

                if (
                    w_max == 0.0
                    or d_w_max / w_max <= d_w_tol
                    or n_iter == max_iter - 1
                    or n_active <= 1  # We have an analytical exact solution.
                ):
                    if center and R_offset != 0:
                        _flush_R_offset(n_samples, R, sample_weight, no_sample_weights,
                                        R_offset)
                        R_offset = 0.0
                        R_version += 1
                    # The candidates are the features not excluded at this alpha.
                    gap, dual_norm_XtA = gap_enet_sparse_lazy(
                        n_samples, n_features, w, alpha, beta, X_data, X_indices,
                        X_indptr, y, inv_sample_weight, no_sample_weights, X_mean,
                        center, R, R_sum, R_version, XtR, XtR_version, XtA, active_set,
                        n_active, full_gap, R_ref, XtA_ref, X_col_norms, ZtR, positive,
                        True, &full_gap, &R_l2, R_stats, &R_stats_version,
                    )
                    d_R_bound = 0.0

                    if gap <= tol_scaled:
                        # return if we reached desired tolerance
                        break

                    # Gap Safe Screening Rules, see https://arxiv.org/abs/1802.07481
                    if screening:
                        n_active = 0
                        for j in range(n_features):
                            if excluded_set[j]:
                                continue
                            Xj_theta = XtA[j] / fmax(alpha, dual_norm_XtA)
                            d_j = (1 - fabs(Xj_theta)) / sqrt(norm2_cols_X[j] + beta)
                            if d_j <= sqrt(2 * gap) / alpha:
                                active_set[n_active] = j
                                excluded_set[j] = 0
                                n_active += 1
                            else:
                                if w[j] != 0:
                                    # R += w[j] * X[:,j]
                                    _sparse_R_add(R, X_data, X_indices, X_indptr,
                                                  sample_weight, no_sample_weights,
                                                  w[j], j)
                                    R_offset -= w[j] * X_mean[j]
                                    R_version += 1
                                    d_R_bound += fabs(w[j]) * update_norms[j]
                                    w[j] = 0
                                excluded_set[j] = 1
            else:
                converged = False

            # R of the coefficients of this alpha for the next alpha
            if center and R_offset != 0:
                _flush_R_offset(n_samples, R, sample_weight, no_sample_weights,
                                R_offset)
                R_version += 1
            R_offset = 0.0
            if not screening:
                # all features are candidates of the next dual gap
                n_active = n_features
                for j in range(n_features):
                    active_set[j] = j

        coefs[:, i_alpha] = w
        gaps[i_alpha] = gap
        n_iters[i_alpha] = n_iter + 1
        if not converged:
            _warn_not_converged(alpha, gap, tol_scaled)

    return tol_scaled


cdef inline floating _small_nrm2(unsigned int n, const floating* x) noexcept nogil:
    """sqrt(x @ x) for the short vectors of the tasks, without a BLAS call."""
    cdef unsigned int t
    cdef floating s = 0.0
    for t in range(n):
        s += x[t] * x[t]
    return sqrt(s)


cdef (floating, floating) gap_enet_multi_task_sparse_XtR(
    unsigned int n_samples,
    unsigned int n_features,
    unsigned int n_tasks,
    const floating[::1, :] W,
    floating alpha,  # L1 penalty
    floating beta,  # L2 penalty
    const floating[:, ::1] Y,  # C-ordered copy of Y
    const floating[::1] inv_sample_weight,
    bint no_sample_weights,
    const floating[::1] X_mean,
    bint center,
    const floating[:, ::1] R,  # C-ordered residuals sw * (Y - Z @ W.T)
    const floating[::1] R_sum,
    const floating[:, ::1] XtR,  # X.T @ R, with X not centered
    floating[:, ::1] XtA,  # out
    floating[::1] XtA_row_norms,  # out
    bint gap_smaller_eps,
) noexcept nogil:
    """Dual gap of gap_enet_multi_task for sparse X, given XtR = X.T @ R."""
    cdef floating gap, primal, dual
    cdef floating dual_norm_XtA
    cdef floating R_norm2
    cdef floating Ry = 0.0
    cdef floating w_l21_norm
    cdef floating w_l2_norm2 = 0.0
    cdef unsigned int i, t, j

    if floating is float:
        eps = FLT_EPSILON
    else:
        eps = DBL_EPSILON

    # w_l2_norm2 = linalg.norm(W, ord="fro") ** 2
    if beta > 0:
        w_l2_norm2 = _dot(n_features * n_tasks, &W[0, 0], 1, &W[0, 0], 1)
    # R_norm2 = linalg.norm(R, ord="fro") ** 2, with sample weights of R / sw
    if no_sample_weights:
        R_norm2 = _dot(n_samples * n_tasks, &R[0, 0], 1, &R[0, 0], 1)
    else:
        R_norm2 = 0.0
        for i in range(n_samples):
            # inv_sample_weight is 0 where sample_weight is 0
            for t in range(n_tasks):
                R_norm2 += (R[i, t] ** 2) * inv_sample_weight[i]
    # Ry = np.sum(R * Y)
    if not (alpha == 0 and beta == 0):
        Ry = _dot(n_samples * n_tasks, &R[0, 0], 1, &Y[0, 0], 1)

    if alpha == 0:
        # XtA = Z.T @ R
        for j in range(n_features):
            for t in range(n_tasks):
                XtA[j, t] = XtR[j, t]
                if center:
                    XtA[j, t] -= X_mean[j] * R_sum[t]
        dual_norm_XtA = _dot(n_features * n_tasks, &XtA[0, 0], 1, &XtA[0, 0], 1)
        if beta == 0:
            gap = dual_norm_XtA
            return gap, dual_norm_XtA
        primal = 0.5 * (R_norm2 + beta * w_l2_norm2)
        dual = -0.5 * R_norm2 + Ry - 1 / (2 * beta) * dual_norm_XtA
        gap = primal - dual
        if gap_smaller_eps and abs(gap) <= 2 * eps * primal:
            gap = 0.0
        return gap, dual_norm_XtA

    # XtA = Z.T @ R - beta * W.T
    dual_norm_XtA = 0.0
    for j in range(n_features):
        for t in range(n_tasks):
            XtA[j, t] = XtR[j, t]
            if center:
                XtA[j, t] -= X_mean[j] * R_sum[t]
            XtA[j, t] -= beta * W[t, j]
        # dual_norm_XtA = np.max(np.sqrt(np.sum(XtA ** 2, axis=1)))
        XtA_row_norms[j] = _small_nrm2(n_tasks, &XtA[j, 0])
        if XtA_row_norms[j] > dual_norm_XtA:
            dual_norm_XtA = XtA_row_norms[j]

    # w_l21_norm = np.sqrt(np.sum(W ** 2, axis=0)).sum()
    w_l21_norm = 0.0
    for j in range(n_features):
        w_l21_norm += _small_nrm2(n_tasks, &W[0, j])

    gap = dual_gap_formulation_A(
        alpha=alpha,
        beta=beta,
        w_l1_norm=w_l21_norm,
        w_l2_norm2=w_l2_norm2,
        R_norm2=R_norm2,
        Ry=Ry,
        dual_norm_XtA=dual_norm_XtA,
        gap_smaller_eps=gap_smaller_eps,
    )
    return gap, dual_norm_XtA


cdef inline void _multi_task_col_dot(
    unsigned int n_tasks,
    const floating* R,  # C-ordered, of shape (n_samples, n_tasks)
    const floating[::1] X_data,
    const int32_t[::1] X_indices,
    int32_t startptr,
    int32_t endptr,
    floating* out,  # shape (n_tasks,)
) noexcept nogil:
    """out = X[:, j] @ R for the nonzero entries X_data[startptr:endptr] of X[:, j].

    Each task is summed in the order of the nonzero entries. Up to 4 tasks are summed
    in one pass over the entries.
    """
    cdef unsigned int t
    cdef int32_t i_ind
    cdef floating x
    cdef const floating* r
    cdef floating a0 = 0.0, a1 = 0.0, a2 = 0.0, a3 = 0.0
    if n_tasks == 1:
        for i_ind in range(startptr, endptr):
            a0 += X_data[i_ind] * R[X_indices[i_ind]]
        out[0] = a0
    elif n_tasks == 2:
        for i_ind in range(startptr, endptr):
            x = X_data[i_ind]
            r = R + 2 * X_indices[i_ind]
            a0 += x * r[0]
            a1 += x * r[1]
        out[0] = a0
        out[1] = a1
    elif n_tasks == 3:
        for i_ind in range(startptr, endptr):
            x = X_data[i_ind]
            r = R + 3 * X_indices[i_ind]
            a0 += x * r[0]
            a1 += x * r[1]
            a2 += x * r[2]
        out[0] = a0
        out[1] = a1
        out[2] = a2
    elif n_tasks == 4:
        for i_ind in range(startptr, endptr):
            x = X_data[i_ind]
            r = R + 4 * X_indices[i_ind]
            a0 += x * r[0]
            a1 += x * r[1]
            a2 += x * r[2]
            a3 += x * r[3]
        out[0] = a0
        out[1] = a1
        out[2] = a2
        out[3] = a3
    else:
        for t in range(n_tasks):
            a0 = 0.0
            for i_ind in range(startptr, endptr):
                a0 += X_data[i_ind] * R[X_indices[i_ind] * n_tasks + t]
            out[t] = a0


cdef inline void _multi_task_XtR(
    unsigned int n_features,
    unsigned int n_tasks,
    const floating[::1] X_data,
    const int32_t[::1] X_indices,
    const int32_t[::1] X_indptr,
    const floating[:, ::1] R,
    floating[:, ::1] XtR,  # out
) noexcept nogil:
    """XtR = X.T @ R for sparse CSC X and C-ordered R."""
    cdef unsigned int j
    for j in range(n_features):
        _multi_task_col_dot(n_tasks, &R[0, 0], X_data, X_indices, X_indptr[j],
                            X_indptr[j + 1], &XtR[j, 0])


cdef inline void _multi_task_R_add(
    unsigned int n_tasks,
    floating[:, ::1] R,  # inout
    const floating[::1] X_data,
    const int32_t[::1] X_indices,
    const int32_t[::1] X_indptr,
    const floating[::1] sample_weight,
    bint no_sample_weights,
    const floating* w_j,  # shape (n_tasks,)
    unsigned int j,
) noexcept nogil:
    """R += sample_weight * X[:, j] * w_j[None, :] on the nonzero entries of X[:, j]."""
    cdef unsigned int t
    cdef int32_t i, i_ind
    cdef floating x
    for i_ind in range(X_indptr[j], X_indptr[j + 1]):
        i = X_indices[i_ind]
        if no_sample_weights:
            x = X_data[i_ind]
            for t in range(n_tasks):
                R[i, t] += x * w_j[t]
        else:
            for t in range(n_tasks):
                R[i, t] += sample_weight[i] * X_data[i_ind] * w_j[t]


cdef inline void _multi_task_flush_R_offset(
    unsigned int n_samples,
    unsigned int n_tasks,
    floating[:, ::1] R,  # inout
    const floating[::1] sample_weight,
    bint no_sample_weights,
    floating[::1] R_offset,  # inout, reset to 0
) noexcept nogil:
    """R += sample_weight[:, None] * R_offset[None, :] and set R_offset to 0."""
    cdef unsigned int i, t
    for i in range(n_samples):
        if no_sample_weights:
            for t in range(n_tasks):
                R[i, t] += R_offset[t]
        else:
            for t in range(n_tasks):
                R[i, t] += sample_weight[i] * R_offset[t]
    for t in range(n_tasks):
        R_offset[t] = 0.0


def enet_coordinate_descent_multi_task_sparse_path(
    floating[::1, :] W,
    const floating[::1] l1_regs,
    const floating[::1] l2_regs,
    const floating[::1] X_data,
    const int32_t[::1] X_indices,
    const int32_t[::1] X_indptr,
    const floating[::1, :] Y,
    const floating[::1] sample_weight,
    const floating[::1] X_mean,
    floating[:, :, :] coefs,
    floating[::1] gaps,
    int32_t[::1] n_iters,
    unsigned int max_iter,
    floating tol,
    object rng,
    bint random=0,
    bint do_screening=1,
    bint early_stopping=1,
):
    """Coordinate descent for multi-task Elastic-Net on sparse X along a path.

    Fits, for every k, the problem of `enet_coordinate_descent_multi_task` with sparse
    X, alpha = l1_regs[k] and beta = l2_regs[k], warm started at the solution of
    k - 1, with the same iterations, convergence checks and screening rules.

    Parameters
    ----------
    W : ndarray of shape (n_tasks, n_features), Fortran-ordered
        Initial coefficients, holds the coefficients of the last alpha on exit.
    l1_regs, l2_regs : ndarray of shape (n_alphas,)
        L1 and L2 penalties alpha and beta of the path (already multiplied by
        n_samples).
    coefs : ndarray of shape (n_tasks, n_features, n_alphas)
        Output, coefficients at each alpha.
    gaps : ndarray of shape (n_alphas,)
        Output, dual gap at each alpha.
    n_iters : ndarray of shape (n_alphas,)
        Output, number of iterations at each alpha.

    The other parameters are those of `enet_coordinate_descent_multi_task` with
    X_is_sparse=True.

    Returns
    -------
    tol : float
        Equals input `tol` times `np.sum(Y * sample_weight[:, None] * Y)`. The
        tolerance used for the dual gap.
    """
    # The residuals R are stored C-ordered, of shape (n_samples, n_tasks), such that a
    # coordinate update visits each nonzero entry of X[:, j] once for all tasks. As in
    # enet_coordinate_descent_sparse_path, the centering part of the updates is summed
    # up in R_offset of shape (n_tasks,): the residuals are
    # R + sample_weight[:, None] * R_offset[None, :], and
    #     X[:, j] @ (R + sw[:, None] * R_offset) = X[:, j] @ R + X_sw_sum[j] * R_offset
    # R_offset is added to R before each dual gap and at the end of each alpha.
    # XtR = X.T @ R (X not centered) of the current R is kept from one alpha to the
    # next.
    if floating is float:
        dtype = np.float32
    else:
        dtype = np.float64

    cdef unsigned int n_samples = Y.shape[0]
    cdef unsigned int n_features = W.shape[1]
    cdef unsigned int n_tasks = Y.shape[1]
    cdef unsigned int n_alphas = l1_regs.shape[0]
    cdef bint no_sample_weights = sample_weight is None
    cdef floating[::1] norm2_cols_X = np.empty(n_features, dtype=dtype)
    cdef floating[::1] X_sw_sum = np.empty(n_features, dtype=dtype)
    cdef floating[:, ::1] Y_c = np.ascontiguousarray(Y, dtype=dtype)
    cdef floating[:, ::1] R
    cdef floating[:, ::1] XtR = np.empty((n_features, n_tasks), dtype=dtype)
    cdef floating[:, ::1] XtA = np.empty((n_features, n_tasks), dtype=dtype)
    cdef floating[::1] XtA_row_norms = np.empty(n_features, dtype=dtype)
    cdef floating[::1] inv_sample_weight = None
    cdef floating[::1] R_sum = np.zeros(n_tasks, dtype=dtype)
    cdef floating[::1] R_offset = np.zeros(n_tasks, dtype=dtype)
    cdef floating[::1] tmp = np.empty(n_tasks, dtype=dtype)
    cdef floating[::1] w_j = np.empty(n_tasks, dtype=dtype)
    cdef floating[::1] d_w = np.empty(n_tasks, dtype=dtype)
    cdef uint32_t[::1] active_set = np.empty(n_features, dtype=np.uint32)
    cdef uint8_t[::1] excluded_set = np.zeros(n_features, dtype=np.uint8)

    cdef floating alpha, beta
    cdef floating d_j
    cdef floating Xj_theta
    cdef floating d_w_max
    cdef floating w_max
    cdef floating d_w_j
    cdef floating nn
    cdef floating scale
    cdef floating W_j_abs_max
    cdef floating gap
    cdef floating d_w_tol = tol
    cdef floating tol_scaled
    cdef floating dual_norm_XtA
    cdef floating X_mean_j
    cdef floating sw
    cdef floating sw_sum = 0.0
    cdef floating normalize_sum
    cdef floating X_sw_sum_j
    cdef unsigned int n_active
    cdef int32_t i, i_ind, startptr, endptr
    cdef unsigned int j, t
    cdef unsigned int n_iter
    cdef unsigned int f_iter
    cdef unsigned int i_alpha
    cdef uint32_t rand_r_state_seed
    cdef uint32_t* rand_r_state = &rand_r_state_seed
    cdef bint center = False
    cdef bint screening
    cdef bint converged
    cdef bint changed
    cdef bint XtR_stale = False

    if no_sample_weights:
        R = np.array(Y_c, dtype=dtype)
    else:
        R = np.multiply(np.asarray(sample_weight)[:, None], Y_c)
        inv_sample_weight = np.zeros(n_samples, dtype=dtype)

    with nogil:
        # center = (X_mean != 0).any()
        for j in range(n_features):
            if X_mean[j]:
                center = True
                break

        if no_sample_weights:
            sw_sum = n_samples
        else:
            for i in range(n_samples):
                sw_sum += sample_weight[i]
                if sample_weight[i] != 0:
                    inv_sample_weight[i] = 1 / sample_weight[i]

        # tol = tol * linalg.norm(Y, ord='fro') ** 2
        # with sample weights: tol *= y @ (sw * y)
        tol_scaled = tol * _dot(n_samples * n_tasks, &Y_c[0, 0], 1, &R[0, 0], 1)

        # norm2_cols_X = np.sum(sw * (X - X_mean)**2, axis=0)
        # X_sw_sum = np.sum(sw * X, axis=0)
        for j in range(n_features):
            X_mean_j = X_mean[j]
            startptr = X_indptr[j]
            endptr = X_indptr[j + 1]
            normalize_sum = 0.0
            X_sw_sum_j = 0.0
            if no_sample_weights:
                for i_ind in range(startptr, endptr):
                    normalize_sum += (X_data[i_ind] - X_mean_j) ** 2
                    X_sw_sum_j += X_data[i_ind]
                if center:
                    normalize_sum += (n_samples - endptr + startptr) * X_mean_j ** 2
            else:
                for i_ind in range(startptr, endptr):
                    i = X_indices[i_ind]
                    sw = sample_weight[i]
                    normalize_sum += sw * (
                        (X_data[i_ind] - X_mean_j) ** 2 - X_mean_j ** 2
                    )
                    X_sw_sum_j += sw * X_data[i_ind]
                if center:
                    normalize_sum += sw_sum * X_mean_j ** 2
            norm2_cols_X[j] = normalize_sum
            X_sw_sum[j] = X_sw_sum_j

            # R = sw * (Y - X @ W.T), the centering part goes to R_offset
            changed = False
            for t in range(n_tasks):
                d_w[t] = -W[t, j]
                changed = changed or W[t, j] != 0
                R_offset[t] += X_mean_j * W[t, j]
            if changed:
                _multi_task_R_add(n_tasks, R, X_data, X_indices, X_indptr,
                                  sample_weight, no_sample_weights, &d_w[0], j)

        if center:
            _multi_task_flush_R_offset(n_samples, n_tasks, R, sample_weight,
                                       no_sample_weights, R_offset)
            # R_sum = np.sum(R, axis=0). It does not change in the coordinate updates,
            # as w_j[t] * np.sum(sw * (X[:, j] - X_mean[j])) = 0.
            for i in range(n_samples):
                for t in range(n_tasks):
                    R_sum[t] += R[i, t]
        for t in range(n_tasks):
            R_offset[t] = 0.0

        _multi_task_XtR(n_features, n_tasks, X_data, X_indices, X_indptr, R, XtR)

    for i_alpha in range(n_alphas):
        alpha = l1_regs[i_alpha]
        beta = l2_regs[i_alpha]
        rand_r_state_seed = rng.randint(0, RAND_R_MAX)
        screening = do_screening and alpha != 0
        converged = True
        n_active = n_features

        with nogil:
            # Check convergence before entering the main loop.
            gap, dual_norm_XtA = gap_enet_multi_task_sparse_XtR(
                n_samples, n_features, n_tasks, W, alpha, beta, Y_c,
                inv_sample_weight, no_sample_weights, X_mean, center, R, R_sum, XtR,
                XtA, XtA_row_norms, gap_smaller_eps=False,
            )
            if early_stopping and gap <= tol_scaled:
                n_iter = 0
            else:
                n_iter = 1
        if n_iter == 0:
            coefs[:, :, i_alpha] = W
            gaps[i_alpha] = gap
            n_iters[i_alpha] = 0
            continue

        with nogil:
            # Gap Safe Screening Rules for multi-task Lasso, see
            # https://arxiv.org/abs/1703.07285 Eq 2.2. (also arxiv:1506.03736)
            if screening:
                n_active = 0
                for j in range(n_features):
                    if norm2_cols_X[j] == 0:
                        for t in range(n_tasks):
                            W[t, j] = 0
                        excluded_set[j] = 1
                        continue
                    Xj_theta = XtA_row_norms[j] / fmax(alpha, dual_norm_XtA)
                    d_j = (1 - Xj_theta) / sqrt(norm2_cols_X[j] + beta)
                    if d_j <= sqrt(2 * gap) / alpha:
                        active_set[n_active] = j
                        excluded_set[j] = 0
                        n_active += 1
                    else:
                        # R += W[:, j] * X[:, j][:, None]
                        changed = False
                        for t in range(n_tasks):
                            changed = changed or W[t, j] != 0
                            R_offset[t] -= W[t, j] * X_mean[j]
                        if changed:
                            _multi_task_R_add(n_tasks, R, X_data, X_indices, X_indptr,
                                              sample_weight, no_sample_weights,
                                              &W[0, j], j)
                            XtR_stale = True
                        for t in range(n_tasks):
                            W[t, j] = 0
                        excluded_set[j] = 1

            n_iter = 0
            for n_iter in range(max_iter):
                w_max = 0.0
                d_w_max = 0.0
                for f_iter in range(n_active):  # Loop over coordinates
                    if random:
                        j = rand_int(n_active, rand_r_state)
                    else:
                        j = f_iter

                    if screening:
                        j = active_set[j]

                    if norm2_cols_X[j] == 0.0:
                        continue

                    # tmp = X[:, j] @ (R + w_j * X[:,j][:, None])
                    _multi_task_col_dot(n_tasks, &R[0, 0], X_data, X_indices,
                                        X_indptr[j], X_indptr[j + 1], &tmp[0])
                    for t in range(n_tasks):
                        # w_j = W[:, j] # Store previous value
                        w_j[t] = W[t, j]
                        if center:
                            # contribution of R_offset, see the notes above
                            tmp[t] += R_offset[t] * X_sw_sum[j]
                        tmp[t] += w_j[t] * norm2_cols_X[j]

                    # nn = sqrt(np.sum(tmp ** 2))
                    nn = _small_nrm2(n_tasks, &tmp[0])

                    # W[:, j] = tmp * fmax(1. - alpha / nn, 0) / (norm2_cols_X[j] + beta)
                    scale = fmax(1. - alpha / nn, 0) / (norm2_cols_X[j] + beta)
                    for t in range(n_tasks):
                        W[t, j] = tmp[t] * scale

                    # Update residual: R -= (W[:, j] - w_j) * X[:, j][:, None]
                    changed = False
                    for t in range(n_tasks):
                        d_w[t] = w_j[t] - W[t, j]
                        if d_w[t] != 0:
                            changed = True
                            R_offset[t] -= d_w[t] * X_mean[j]
                    if changed:
                        _multi_task_R_add(n_tasks, R, X_data, X_indices, X_indptr,
                                          sample_weight, no_sample_weights, &d_w[0], j)
                        XtR_stale = True

                    # update the maximum absolute coefficient update
                    d_w_j = diff_abs_max(n_tasks, &W[0, j], &w_j[0])

                    if d_w_j > d_w_max:
                        d_w_max = d_w_j

                    W_j_abs_max = abs_max(n_tasks, &W[0, j])
                    if W_j_abs_max > w_max:
                        w_max = W_j_abs_max

                if (
                    w_max == 0.0
                    or d_w_max / w_max <= d_w_tol
                    or n_iter == max_iter - 1
                    or n_active <= 1  # We have an analytical exact solution.
                ):
                    if center:
                        _multi_task_flush_R_offset(n_samples, n_tasks, R,
                                                   sample_weight, no_sample_weights,
                                                   R_offset)
                    if XtR_stale:
                        _multi_task_XtR(n_features, n_tasks, X_data, X_indices,
                                        X_indptr, R, XtR)
                        XtR_stale = False
                    gap, dual_norm_XtA = gap_enet_multi_task_sparse_XtR(
                        n_samples, n_features, n_tasks, W, alpha, beta, Y_c,
                        inv_sample_weight, no_sample_weights, X_mean, center, R,
                        R_sum, XtR, XtA, XtA_row_norms, gap_smaller_eps=True,
                    )
                    if gap <= tol_scaled:
                        # return if we reached desired tolerance
                        break

                    # Gap Safe Screening Rules for multi-task Lasso, see
                    # https://arxiv.org/abs/1703.07285 Eq 2.2. (also arxiv:1506.03736)
                    if screening:
                        n_active = 0
                        for j in range(n_features):
                            if excluded_set[j]:
                                continue
                            Xj_theta = XtA_row_norms[j] / fmax(alpha, dual_norm_XtA)
                            d_j = (1 - Xj_theta) / sqrt(norm2_cols_X[j] + beta)
                            if d_j <= sqrt(2 * gap) / alpha:
                                active_set[n_active] = j
                                excluded_set[j] = 0
                                n_active += 1
                            else:
                                # R += W[:, j] * X[:, j][:, None]
                                changed = False
                                for t in range(n_tasks):
                                    changed = changed or W[t, j] != 0
                                    R_offset[t] -= W[t, j] * X_mean[j]
                                if changed:
                                    _multi_task_R_add(n_tasks, R, X_data, X_indices,
                                                      X_indptr, sample_weight,
                                                      no_sample_weights, &W[0, j], j)
                                    XtR_stale = True
                                for t in range(n_tasks):
                                    W[t, j] = 0
                                excluded_set[j] = 1
            else:
                converged = False

            # R and XtR of the coefficients of this alpha for the next alpha
            if center:
                _multi_task_flush_R_offset(n_samples, n_tasks, R, sample_weight,
                                           no_sample_weights, R_offset)
            if XtR_stale:
                _multi_task_XtR(n_features, n_tasks, X_data, X_indices, X_indptr, R,
                                XtR)
                XtR_stale = False

        coefs[:, :, i_alpha] = W
        gaps[i_alpha] = gap
        n_iters[i_alpha] = n_iter + 1
        if not converged:
            _warn_not_converged(alpha, gap, tol_scaled)

    return tol_scaled
