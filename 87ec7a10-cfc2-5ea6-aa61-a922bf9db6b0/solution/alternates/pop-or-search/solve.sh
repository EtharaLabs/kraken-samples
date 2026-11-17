#!/usr/bin/env bash
# Alternate correct solution: leave pop_op_eqns as it is and give the wrapper
# constructors their own removal helper in pennylane/core/queuing.py. A consumed
# operator's equation is nearly always the newest entry of its frame, so that slot is
# checked first; any other position falls back to the full filter of the frame.
set -euo pipefail
python3 - /app/pennylane/pennylane <<'PY'
import sys
from pathlib import Path

root = Path(sys.argv[1])


def swap(rel, old, new):
    path = root / rel
    text = path.read_text()
    if text.count(old) != 1:
        raise SystemExit(f"{rel}: expected exactly one occurrence of {old.splitlines()[0]!r}")
    path.write_text(text.replace(old, new))
    print(f"edited {rel}")


swap(
    "core/queuing.py",
    '''def remove_from_program(op):
    """Removes an operator from the captured/queued program."""
    if QueuingManager.recording():
        QueuingManager.remove(op)
    if capture.enabled():
        # pylint: disable-next=import-outside-toplevel
        from .operator.operator2 import pop_op_eqns  # tach-ignore

        pop_op_eqns((op,))
''',
    '''def drop_captured_eqns(ops) -> list:
    """Remove the captured equations of ``ops`` and detach their tracers.

    Returns the removed equations in the order of ``ops``. When a frame loses a single
    operator, its entries are searched from the newest backwards and the search stops at the
    first entry whose equation is the target, deleting only that entry; the newest slot is
    therefore found at once. A frame that loses several operators is filtered once against
    all of its targets.
    """
    gone = []
    by_frame = {}
    for op in ops:
        tracer = getattr(op, "tracer", None)
        if tracer is None:
            continue
        frame = tracer._trace.frame  # pylint: disable=protected-access
        if frame.auto_dce:
            raise ValueError("drop_captured_eqns needs a tracing frame without auto_dce")
        target = tracer.parent
        gone.append(target)
        by_frame.setdefault(id(frame), (frame, []))[1].append(target)
        op.tracer = None
    for frame, targets in by_frame.values():
        slots = frame.tracing_eqns
        if len(targets) == 1:
            target = targets[0]
            for position in range(len(slots) - 1, -1, -1):
                if slots[position]() is target:
                    del slots[position]
                    break
            continue
        keys = {id(target) for target in targets}
        frame.tracing_eqns = [slot for slot in slots if id(slot()) not in keys]
    return gone


def remove_from_program(op):
    """Removes an operator from the captured/queued program."""
    if QueuingManager.recording():
        QueuingManager.remove(op)
    if capture.enabled():
        drop_captured_eqns((op,))


def remove_many_from_program(ops):
    """Removes several operators from the captured/queued program with one equation sweep."""
    ops = tuple(ops)
    if QueuingManager.recording():
        for op in ops:
            QueuingManager.remove(op)
    if capture.enabled():
        drop_captured_eqns(ops)
''',
)
swap(
    "ops/op_math/controlled.py",
    "from pennylane.core.operator.operator2 import pop_op_eqns  # tach-ignore\n",
    "from pennylane.core.queuing import drop_captured_eqns\n",
)
swap(
    "ops/op_math/controlled.py",
    "    qp.QueuingManager.remove(op)\n    _ = pop_op_eqns((op,))\n",
    "    qp.QueuingManager.remove(op)\n    drop_captured_eqns((op,))\n",
)
swap(
    "ops/op_math/controlled2.py",
    "    operator_p,\n    pop_op_eqns,\n)\nfrom pennylane.core.queuing import remove_from_program\n",
    "    operator_p,\n)\nfrom pennylane.core.queuing import drop_captured_eqns, remove_from_program\n",
)
swap(
    "ops/op_math/controlled2.py",
    "        eqns = pop_op_eqns((self.base,))\n        assert len(eqns) == 1,",
    "        eqns = drop_captured_eqns((self.base,))\n        assert len(eqns) == 1,",
)
swap(
    "ops/op_math/adjoint.py",
    "from pennylane.core.queuing import QueuingManager\n",
    "from pennylane.core.queuing import QueuingManager, drop_captured_eqns\n",
)
swap(
    "ops/op_math/adjoint.py",
    "    if isinstance(op, Operator2):\n        _ = pop_op_eqns((op,))\n        return Adjoint2(op)\n",
    "    if isinstance(op, Operator2):\n        drop_captured_eqns((op,))\n        return Adjoint2(op)\n",
)

swap(
    "core/queuing.py",
    '__all__ = ["QueuingManager", "AnnotatedQueue", "remove_from_program"]\n',
    '__all__ = [\n'
    '    "QueuingManager",\n'
    '    "AnnotatedQueue",\n'
    '    "remove_from_program",\n'
    '    "remove_many_from_program",\n'
    '    "drop_captured_eqns",\n'
    ']\n',
)
swap(
    "ops/op_math/composite2.py",
    "from pennylane.queuing import remove_from_program\n",
    "from pennylane.queuing import remove_from_program, remove_many_from_program\n",
)
swap(
    "ops/op_math/composite2.py",
    "        for op in self:\n            remove_from_program(op)\n\n    # FIX",
    "        remove_many_from_program(self)\n\n    # FIX",
)
swap(
    "ops/op_math/prod.py",
    "from pennylane.core.queuing import QueuingManager, remove_from_program\n",
    "from pennylane.core.queuing import QueuingManager, remove_many_from_program\n",
)
swap(
    "ops/op_math/prod.py",
    "        for op in ops:\n            remove_from_program(op)\n\n        return Prod2(operands)",
    "        remove_many_from_program(ops)\n\n        return Prod2(operands)",
)
PY
