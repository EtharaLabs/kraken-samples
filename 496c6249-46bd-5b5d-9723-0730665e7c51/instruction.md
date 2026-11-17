# Make set membership on variable-width string arrays fast

## Background

A development checkout of NumPy lives at `/app/numpy`. It is installed in
editable mode into the `python` on your `PATH`: a saved change to a Python file
is picked up the next time `numpy` is imported, and a change to C source is
recompiled when `numpy` is next imported (you can also recompile explicitly with
`ninja -C /app/numpy/build`). Run your scripts from outside the checkout (for
example from `/app`), because importing `numpy` with `/app/numpy` as the current
directory finds the uncompiled source folder instead of the build.

NumPy's variable-width string dtype, `numpy.dtypes.StringDType`, can optionally
carry a missing-value sentinel (`StringDType(na_object=...)`). Membership tests on
arrays of this dtype are very slow: `np.isin` on a few tens of thousands of
strings takes seconds, and the routines that rely on it slow down with it. Arrays
that use a missing-value sentinel are hit hardest.

## Seeing the problem

```
cd /app && python /app/workload/isin_workload.py
```

The script times one `np.isin` call on two seeded string arrays for three
settings (no sentinel, `None` as the sentinel, `nan` as the sentinel) and prints
a digest of each result.

## What to deliver

Change NumPy's library code under `/app/numpy/numpy/` so that membership tests on
`StringDType` arrays become much faster. Your work is accepted when all of these
hold:

1. `np.isin` on large `StringDType` arrays is much faster than now, both with and
   without a missing-value sentinel, whatever kind of object the sentinel is, and
   also when one operand is a fixed-width unicode (`U`) array, on arrays beyond
   the script's, on the first call in a new Python process.
2. Every result is exactly what the current library returns, for every dtype,
   every kind of sentinel, every mix of operands, every keyword argument, and
   every routine that builds on membership tests (`setdiff1d`, `intersect1d`,
   `union1d`, `setxor1d`, `unique`).
3. NumPy still builds from source, and its existing tests for string dtypes and
   set routines still pass.
4. The change reads like normal upstream code.

## Constraints

- Only files inside `/app/numpy/numpy/` count; leave NumPy's test files,
  benchmarks, test configuration and the workload script alone.
- Do not keep results between calls or processes (no caches or memoization in
  files, shared memory, module state or a background process).
- Code must not change its behaviour based on the call stack, environment
  variables, command-line arguments, file paths or files outside the library.
- Nothing may be tailored to the workload script's inputs, sizes or seed.
- Keep the public signatures and documented behaviour of `np.isin` and the other
  set routines as they are.
- The sandbox is offline. Do not install, reinstall or upgrade packages.
