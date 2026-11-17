"""One family run in a fresh interpreter, against the Cirq tree on sys.path.

usage: child.py <tree> <family> <seed> <count>

Builds `count` hidden cases of the family from the seed, times each entry-point call
once (the call and a walk over its result), and prints one JSON line with the
timings, a digest of each input and a plain-data dump of each output.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time


def _num(z: complex) -> list[float]:
    return [round(float(z.real), 12), round(float(z.imag), 12)]


def dump_circuit(cirq, circuit) -> list:
    out = []
    for moment in circuit:
        ops = []
        for op in moment:
            rec = {
                "q": [str(q) for q in op.qubits],
                "t": sorted(str(t) for t in op.tags),
            }
            inner = op.untagged
            if isinstance(inner, cirq.CircuitOperation):
                rec["k"] = "c"
                rec["rep"] = inner.repetitions
                rec["c"] = dump_circuit(cirq, inner.circuit)
            elif not cirq.has_unitary(op):
                rec["k"] = "o"
                rec["v"] = repr(op.untagged)
            elif cirq.num_qubits(op) == 0:
                rec["k"] = "g"
                rec["v"] = _num(cirq.unitary(op)[0, 0])
            else:
                rec["k"] = "u"
                rec["v"] = [_num(z) for z in cirq.unitary(op).flat]
            ops.append(rec)
        out.append(ops)
    return out


def dump(cirq, result) -> dict:
    if isinstance(result, list):
        return {"kind": "matrices", "v": [[_num(z) for z in m.flat] for m in result]}
    return {
        "kind": "circuit",
        "type": type(result).__name__,
        "v": dump_circuit(cirq, result),
    }


def _warm(cirq) -> None:
    q0, q1 = cirq.LineQubit.range(2)
    c = cirq.Circuit(
        cirq.X(q0) ** 0.3,
        cirq.Y(q1) ** 0.2,
        cirq.Z(q0) ** 0.1,
        cirq.CZ(q0, q1),
        cirq.H(q0),
    )
    cirq.merge_single_qubit_gates_to_phxz(c)
    cirq.merge_single_qubit_moments_to_phxz(c)
    cirq.merge_single_qubit_gates_to_phased_x_and_z(c)
    cirq.unitary(
        cirq.CircuitOperation(cirq.FrozenCircuit(cirq.X(q0) ** 0.5, cirq.T(q0)))
    )


def main(argv: list[str]) -> None:
    tree, family, seed, count = argv[0], argv[1], int(argv[2]), int(argv[3])
    sys.path.insert(0, f"{tree}/cirq-core")
    import cirq

    import workloads

    if not cirq.__file__.startswith(tree):
        raise SystemExit(f"cirq imported from {cirq.__file__}, expected {tree}")
    _warm(cirq)
    records = []
    for index in range(count):
        kind, given, call = workloads.cases(cirq, family, seed, index)
        digest = hashlib.sha256(repr(given).encode()).hexdigest()
        t0 = time.perf_counter()
        result = call()
        if not isinstance(result, list):
            for _ in result.all_operations():
                pass
        dt = time.perf_counter() - t0
        records.append(
            {"kind": kind, "seconds": dt, "input": digest, "output": dump(cirq, result)}
        )
    print(json.dumps({"family": family, "seed": seed, "records": records}))


if __name__ == "__main__":
    main(sys.argv[1:])
