#!/usr/bin/env bash
# Alternate correct solution: group the targets of one pop_op_eqns call by frame,
# walk each frame backwards only until every target of that frame has been seen,
# and rebuild just that suffix of the frame's list. Targets sit near the end, so
# the suffix is short and the cost no longer grows with the frame.
set -euo pipefail
python3 - /app/pennylane/pennylane/core/operator/operator2.py <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text()
old = '''def pop_op_eqns(ops: Iterable):
    """Delete the jaxpr equations for operators that have been used as data.

    These equations must be deleted because operators used as data are treated as
    pytrees wrapping dynamic data rather than instructions. Thus, the equation that
    corresponds to the operator as an instruction should be removed.
    """
    old_eqns = []

    for op in ops:
        if op.tracer is not None:
            # pylint: disable=protected-access
            frame = op.tracer._trace.frame
            assert frame.auto_dce is False  # eqns are stored differently if this is enabled

            # for some reason the frame now wraps equations in lambdas
            eqn = op.tracer.parent
            old_eqns.append(eqn)
            frame.tracing_eqns = [r for r in frame.tracing_eqns if r() is not eqn]

            # delete reference to tracer after its equation has been deleted
            op.tracer = None

    return old_eqns
'''
new = '''def _sweep_suffix(frame, doomed: set[int]) -> None:
    """Drop the equations whose ids are in ``doomed`` from the tail of ``frame``.

    The list is read backwards only until every doomed equation has been seen; the suffix
    read that way is rebuilt without them and the prefix before it is left untouched.
    """
    entries = frame.tracing_eqns
    start, seen = len(entries), []
    remaining = len(doomed)
    while remaining and start:
        start -= 1
        resolved = entries[start]()
        seen.append(resolved)
        if id(resolved) in doomed:
            remaining -= 1
    seen.reverse()
    entries[start:] = [
        entry for entry, resolved in zip(entries[start:], seen) if id(resolved) not in doomed
    ]


def pop_op_eqns(ops: Iterable):
    """Delete the jaxpr equations for operators that have been used as data.

    These equations must be deleted because operators used as data are treated as
    pytrees wrapping dynamic data rather than instructions. Thus, the equation that
    corresponds to the operator as an instruction should be removed.

    Targets are grouped by tracing frame and each frame is swept once from its end.
    """
    popped = []
    per_frame: dict[int, tuple[object, set[int]]] = {}
    for op in ops:
        if op.tracer is None:
            continue
        # pylint: disable=protected-access
        frame = op.tracer._trace.frame
        if frame.auto_dce is not False:
            raise NotImplementedError("pop_op_eqns does not support frames with auto_dce")
        eqn = op.tracer.parent
        popped.append(eqn)
        per_frame.setdefault(id(frame), (frame, set()))[1].add(id(eqn))
        op.tracer = None
    for frame, doomed in per_frame.values():
        _sweep_suffix(frame, doomed)
    return popped
'''
if text.count(old) != 1:
    raise SystemExit("pop_op_eqns at the base commit was not found")
path.write_text(text.replace(old, new))
print(f"rewrote pop_op_eqns in {path}")
PY
python3 - /app/pennylane/pennylane/ops/op_math <<'PY2'
# inline batched dequeue: each composite or prod construction drops all its operands at once
import sys
from pathlib import Path

base = Path(sys.argv[1])
block = (
    "        if qp.QueuingManager.recording():\n"
    "            for consumed in {seq}:\n"
    "                qp.QueuingManager.remove(consumed)\n"
    "        if qp.capture.enabled():\n"
    "            # pylint: disable-next=import-outside-toplevel\n"
    "            from pennylane.core.operator.operator2 import pop_op_eqns  # tach-ignore\n"
    "\n"
    "            pop_op_eqns({seq})\n"
)


def replace(name, before, after):
    path = base / name
    text = path.read_text()
    assert text.count(before) == 1, f"{name}: per-operand removal loop not found"
    path.write_text(text.replace(before, after))
    print(f"inlined a batched dequeue in {path}")


replace(
    "composite2.py",
    "        for op in self:\n            remove_from_program(op)\n",
    block.format(seq="tuple(self)"),
)
replace(
    "prod.py",
    "        for op in ops:\n            remove_from_program(op)\n\n        return Prod2(operands)",
    block.format(seq="ops") + "\n        return Prod2(operands)",
)
PY2
