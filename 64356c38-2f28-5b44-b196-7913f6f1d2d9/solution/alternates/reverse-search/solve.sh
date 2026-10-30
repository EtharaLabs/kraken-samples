#!/usr/bin/env bash
# Alternate correct solution: per-operator reverse search with in-place deletion,
# confined to pop_op_eqns. Each consumed operator's equation is found by walking
# its frame's equation list from the newest entry, then deleted where it sits.
set -euo pipefail
python3 - /app/pennylane/pennylane/core/operator/operator2.py <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text()
old = '''    old_eqns = []

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
new = '''    The equation of a consumed operator is almost always among the newest of its frame, so a
    lone target is looked up from the end of the frame's list and deleted in place. When one
    call consumes several operators of a frame, that frame is filtered once against all of them.
    """
    dropped = []
    batches: dict[int, list] = {}
    for op in ops:
        tracer = op.tracer
        if tracer is None:
            continue
        # pylint: disable=protected-access
        frame = tracer._trace.frame
        if frame.auto_dce:
            raise RuntimeError(
                f"Cannot drop the equation of {op}: its tracing frame eliminates dead code."
            )
        # the frame keeps each equation behind a zero-argument callable
        wanted = tracer.parent
        dropped.append(wanted)
        batches.setdefault(id(frame), [frame]).append(wanted)
        op.tracer = None
    for frame, *targets in batches.values():
        thunks = frame.tracing_eqns
        if len(targets) == 1:
            wanted = targets[0]
            for position in range(len(thunks) - 1, -1, -1):
                if thunks[position]() is wanted:
                    del thunks[position]
                    break
        else:
            unwanted = {id(eqn) for eqn in targets}
            thunks[:] = [thunk for thunk in thunks if id(thunk()) not in unwanted]
    return dropped
'''
doc_end = '''    corresponds to the operator as an instruction should be removed.
    """
'''
assert text.count(old) == 1 and text.count(doc_end + old) == 1, "base pop_op_eqns not found"
text = text.replace(doc_end + old, doc_end.removesuffix('    """\n') + "\n" + new)
path.write_text(text)
print(f"rewrote pop_op_eqns in {path}")
PY
python3 - /app/pennylane/pennylane/ops/op_math <<'PY2'
import sys
from pathlib import Path

base = Path(sys.argv[1])


def rewrite(name, before, after):
    path = base / name
    text = path.read_text()
    assert text.count(before) == 1, f"{name}: removal loop not found"
    path.write_text(text.replace(before, after))
    print(f"batched the operand removal in {path}")


helper = (
    "def _forget_operands(operands):\n"
    "    \"\"\"Dequeue ``operands`` and drop their captured equations in one call.\"\"\"\n"
    "    for operand in operands:\n"
    "        if qp.QueuingManager.recording():\n"
    "            qp.QueuingManager.remove(operand)\n"
    "    if qp.capture.enabled():\n"
    "        # pylint: disable-next=import-outside-toplevel\n"
    "        from pennylane.core.operator.operator2 import pop_op_eqns  # tach-ignore\n"
    "\n"
    "        pop_op_eqns(operands)\n"
    "\n\n"
)
rewrite(
    "composite2.py",
    "        for op in self:\n            remove_from_program(op)\n",
    "        _forget_operands(tuple(self))\n",
)
rewrite("composite2.py", "class CompositeOp2(", helper + "class CompositeOp2(")
rewrite(
    "prod.py",
    "        for op in ops:\n            remove_from_program(op)\n\n        return Prod2(operands)",
    "        _forget_operands(ops)\n\n        return Prod2(operands)",
)
rewrite(
    "prod.py",
    "from pennylane.core.queuing import QueuingManager, remove_from_program\n",
    "from pennylane.core.queuing import QueuingManager, remove_from_program\n"
    "from pennylane.ops.op_math.composite2 import _forget_operands\n",
)
PY2
