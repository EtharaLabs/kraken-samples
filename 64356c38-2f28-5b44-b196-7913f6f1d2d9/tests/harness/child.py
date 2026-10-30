"""One measurement in a fresh interpreter.

usage: child.py <tree> family <name> <n> <seed>
       child.py <tree> program <seed>
       child.py <tree> api

Prints one JSON line on stdout. Only the first jax.make_jaxpr call is timed.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time


def _digest(jaxpr) -> str:
    return hashlib.sha256(str(jaxpr).encode()).hexdigest()


def _api(qp, jax) -> dict:
    from pennylane.core.operator.operator2 import pop_op_eqns
    from pennylane.core.queuing import remove_from_program

    def names(jaxpr):
        return [e.params["op_cls"].__name__ for e in jaxpr.eqns]

    out: dict = {}

    def single():
        a = qp.RX(0.25, 0)
        qp.Hadamard(1)
        remove_from_program(a)
        qp.ctrl(qp.T(2), 0)

    out["single_positional"] = names(jax.make_jaxpr(single)())

    def generator():
        ops = [qp.PauliX(0), qp.PauliY(1), qp.PauliZ(2), qp.S(3), qp.T(4)]
        popped = pop_op_eqns(op for i, op in enumerate(ops) if i % 2 == 0)
        out["generator_popped"] = len(popped)
        out["generator_detached"] = [op.tracer is None for op in ops]
        out["generator_again"] = len(pop_op_eqns(iter(ops)))

    out["generator"] = names(jax.make_jaxpr(generator)())

    def nested():
        a = qp.RX(0.5, 0)

        @qp.for_loop(2)
        def loop(i):
            b = qp.RY(0.1 * i, 1)
            qp.PauliZ(2)
            pop_op_eqns([b, a])

        loop()
        qp.CNOT([0, 1])

    out["nested"] = str(jax.make_jaxpr(nested)())

    qp.capture.disable()
    with qp.queuing.AnnotatedQueue() as q:
        a = qp.PauliX(0)
        qp.PauliY(1)
        remove_from_program(a)
    out["queue"] = [type(o).__name__ for o in q.queue]
    return out


def main(argv: list[str]) -> None:
    tree, kind, *rest = argv
    sys.path.insert(0, tree)
    import jax
    import pennylane as qp

    import workloads

    if not qp.__file__.startswith(tree):
        raise SystemExit(f"pennylane imported from {qp.__file__}, expected {tree}")
    qp.capture.enable()
    match kind:
        case "family":
            name, n, seed = rest[0], int(rest[1]), int(rest[2])
            f = workloads.family_program(qp, workloads.family_specs(name, n, seed))
            t0 = time.perf_counter()
            jaxpr = jax.make_jaxpr(f)()
            dt = time.perf_counter() - t0
            print(
                json.dumps(
                    {"seconds": dt, "digest": _digest(jaxpr), "eqns": len(jaxpr.eqns)}
                )
            )
        case "program":
            f = workloads.mixed_program(qp, workloads.program_specs(int(rest[0])))
            jaxpr = jax.make_jaxpr(f)(0.0)
            print(json.dumps({"digest": _digest(jaxpr), "eqns": len(jaxpr.eqns)}))
        case "api":
            out = _api(qp, jax)
            print(
                json.dumps(
                    {
                        "digest": hashlib.sha256(
                            json.dumps(out, sort_keys=True).encode()
                        ).hexdigest(),
                        "detail": out,
                    }
                )
            )
        case _:
            raise SystemExit(f"unknown kind {kind}")


if __name__ == "__main__":
    main(sys.argv[1:])
