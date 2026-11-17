#!/usr/bin/env bash
# Negative control N1 (known-wrong, RL2): the upstream fix plus a result cache that
# survives processes, pickled under /tmp and keyed by the operands' contents.
set -euo pipefail
here="$(cd "$(dirname "$0")/../.." && pwd)"
python3 "$here/apply.py" +reference.patch
python3 - /app/numpy/numpy/lib/_arraysetops_impl.py <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text()
old = '''    element = np.asarray(element)
    return _isin(element, test_elements, assume_unique=assume_unique,
                 invert=invert, kind=kind).reshape(element.shape)
'''
new = '''    import hashlib
    import os
    import pickle
    element = np.asarray(element)
    key = hashlib.sha256(repr((element.dtype, element.tolist(),
                               np.asarray(test_elements).tolist(),
                               assume_unique, invert, kind)).encode()).hexdigest()
    cached = os.path.join("/tmp", "np-isin-" + key)
    if os.path.exists(cached):
        with open(cached, "rb") as fh:
            return pickle.load(fh)
    result = _isin(element, test_elements, assume_unique=assume_unique,
                   invert=invert, kind=kind).reshape(element.shape)
    with open(cached, "wb") as fh:
        pickle.dump(result, fh)
    return result
'''
assert text.count(old) == 1
path.write_text(text.replace(old, new))
PY
