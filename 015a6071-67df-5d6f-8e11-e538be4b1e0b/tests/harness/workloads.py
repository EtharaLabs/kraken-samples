"""Hidden workload generators for the three timed families.

Every circuit is built from (family, seed, index) inside the process that times it,
using only plain gate constructors of the tree under test. Sizes are drawn from the
seed, and the seed is drawn at grading time.
"""

from __future__ import annotations

import random

import numpy as np

ONE_QUBIT_KINDS = ("x", "y", "z", "phx", "phxz", "h", "s", "t", "rx", "ry", "rz")


def _angle(rng: random.Random) -> float:
    return round(rng.uniform(0.05, 0.95), 6) * rng.choice((-1, 1))


def one_qubit_op(cirq, rng: random.Random, q):
    kind = rng.choice(ONE_QUBIT_KINDS)
    match kind:
        case "x":
            return (cirq.X ** _angle(rng)).on(q)
        case "y":
            return (cirq.Y ** _angle(rng)).on(q)
        case "z":
            return (cirq.Z ** _angle(rng)).on(q)
        case "phx":
            return cirq.PhasedXPowGate(
                phase_exponent=_angle(rng), exponent=_angle(rng)
            ).on(q)
        case "phxz":
            return cirq.PhasedXZGate(
                axis_phase_exponent=_angle(rng),
                x_exponent=_angle(rng),
                z_exponent=_angle(rng),
            ).on(q)
        case "h":
            return cirq.H(q)
        case "s":
            return cirq.S(q)
        case "t":
            return cirq.T(q)
        case "rx":
            return cirq.rx(_angle(rng) * 3).on(q)
        case "ry":
            return cirq.ry(_angle(rng) * 3).on(q)
        case _:
            return cirq.rz(_angle(rng) * 3).on(q)


def _grid(cirq, rng: random.Random):
    rows, cols = rng.randint(2, 4), rng.randint(3, 4)
    r0, c0 = rng.randint(0, 6), rng.randint(0, 6)
    return [cirq.GridQubit(r0 + r, c0 + c) for r in range(rows) for c in range(cols)]


def _matching(rng: random.Random, qubits, cirq):
    """A random set of disjoint nearest-neighbour pairs on the grid."""
    present = set(qubits)
    edges = [
        (a, b)
        for a in qubits
        for b in (cirq.GridQubit(a.row + 1, a.col), cirq.GridQubit(a.row, a.col + 1))
        if b in present
    ]
    rng.shuffle(edges)
    used: set = set()
    pairs = []
    for a, b in edges:
        if a not in used and b not in used and rng.random() < 0.8:
            pairs.append((a, b))
            used.update((a, b))
    return pairs or [edges[0]]


def trotter_circuit(cirq, rng: random.Random, cycles: int):
    """A layered trotter-like circuit (one-qubit power gates between CZ layers) put
    through the CZ gauge transformer, in the shape of the upstream benchmark."""
    import numpy as np

    qubits = _grid(cirq, rng)
    n_layers = rng.randint(3, 5)
    gate = rng.choice((cirq.Y, cirq.X))
    exponent = round(rng.uniform(0.1, 0.45), 4)
    moments = []
    for _ in range(n_layers):
        layer_qubits = [q for q in qubits if rng.random() < 0.7] or qubits[:1]
        moments.append(cirq.Moment((gate**exponent).on(q) for q in layer_qubits))
        moments.append(
            cirq.Moment(cirq.CZ(a, b) for a, b in _matching(rng, qubits, cirq))
        )
    circuit = cirq.Circuit.from_moments(*moments) * cycles + cirq.Moment(
        cirq.M(*sorted(qubits))
    )
    gauge = cirq.transformers.gauge_compiling.cz_gauge.CZGaugeTransformer
    return gauge(circuit, prng=np.random.default_rng(rng.randrange(2**32)))


def moment_runs_circuit(cirq, rng: random.Random, blocks: int, *, phases: bool):
    """Runs of single-qubit moments (hidden lengths 2 to 24) separated by two-qubit or
    measurement moments."""
    n = rng.randint(4, 9)
    qubits = cirq.LineQubit.range(n)
    moments = []
    for b in range(blocks):
        for _ in range(rng.randint(2, 24)):
            ops = [one_qubit_op(cirq, rng, q) for q in qubits if rng.random() < 0.75]
            if phases and rng.random() < 0.2:
                ops.append(cirq.GlobalPhaseGate(complex(np.exp(1j * _angle(rng)))).on())
            moments.append(cirq.Moment(ops))
        if rng.random() < 0.8 or b == blocks - 1:
            order = list(qubits)
            rng.shuffle(order)
            moments.append(
                cirq.Moment(cirq.CZ(order[i], order[i + 1]) for i in range(0, n - 1, 2))
            )
        else:
            moments.append(
                cirq.Moment(cirq.measure(q, key=f"m{b}_{q.x}") for q in qubits[:2])
            )
    return cirq.Circuit.from_moments(*moments)


def random_gate_circuit(cirq, rng: random.Random, depth: int):
    """Random one-qubit gates interleaved with CZ and CNOT, op by op."""
    n = rng.randint(3, 7)
    qubits = cirq.LineQubit.range(n)
    ops = []
    for _ in range(depth):
        if rng.random() < 0.25:
            a, b = rng.sample(qubits, 2)
            ops.append(rng.choice((cirq.CZ, cirq.CNOT))(a, b))
        else:
            ops.append(one_qubit_op(cirq, rng, rng.choice(qubits)))
    return cirq.Circuit(ops)


def one_qubit_circuit_ops(cirq, rng: random.Random, count: int):
    """One-qubit circuit operations (repetitions, inverses, nesting, tags)."""
    out = []
    for i in range(count):
        q = cirq.LineQubit(rng.randint(0, 5))
        body = [one_qubit_op(cirq, rng, q) for _ in range(rng.randint(3, 40))]
        if rng.random() < 0.3:
            inner = cirq.CircuitOperation(
                cirq.FrozenCircuit(
                    one_qubit_op(cirq, rng, q) for _ in range(rng.randint(2, 10))
                ),
                repetitions=rng.choice((1, 2, 3)),
            )
            body.insert(rng.randrange(len(body) + 1), inner)
        op = cirq.CircuitOperation(
            cirq.FrozenCircuit(body), repetitions=rng.choice((1, 1, 2, 3, 5, -1, -2))
        )
        if rng.random() < 0.3:
            op = op.with_tags(f"t{i % 3}")
        out.append(op)
    return out


def deep_circuit(cirq, rng: random.Random, blocks: int, *, phases: bool):
    """Circuits whose ops include multi-qubit circuit operations wrapping runs of
    single-qubit gates; some are tagged "ignore", some one-qubit ops are tagged too."""
    n = rng.randint(3, 6)
    qubits = cirq.LineQubit.range(n)
    ops = []
    for _ in range(blocks):
        sub = []
        for _ in range(rng.randint(4, 14)):
            sub.append(
                cirq.Moment(
                    one_qubit_op(cirq, rng, q) for q in qubits if rng.random() < 0.8
                )
            )
            if phases and rng.random() < 0.2:
                sub.append(
                    cirq.Moment(
                        cirq.GlobalPhaseGate(complex(np.exp(1j * _angle(rng)))).on()
                    )
                )
            if rng.random() < 0.3:
                a, b = rng.sample(qubits, 2)
                sub.append(cirq.Moment(cirq.CZ(a, b)))
        sub.append(cirq.Moment(cirq.CZ(qubits[0], qubits[1])))
        op = cirq.CircuitOperation(cirq.FrozenCircuit.from_moments(*sub))
        if rng.random() < 0.25:
            op = op.with_tags("ignore")
        ops.append(op)
        for q in qubits:
            for _ in range(rng.randint(0, 4)):
                o = one_qubit_op(cirq, rng, q)
                ops.append(o.with_tags("ignore") if rng.random() < 0.1 else o)
    return cirq.Circuit(ops)



def cases(cirq, family: str, seed: int, index: int):
    """One timed case: (entry point name, input, call). The same arguments give the same
    input in every tree."""
    rng = random.Random(f"{family}:{seed}:{index}")
    ctx_ignore = cirq.TransformerContext(deep=True, tags_to_ignore=("ignore",))
    match family:
        case "F1":
            c = trotter_circuit(cirq, rng, rng.randint(150, 260))
            return (
                "merge_single_qubit_gates_to_phxz",
                c,
                lambda: cirq.merge_single_qubit_gates_to_phxz(c),
            )
        case "F2":
            if rng.random() < 0.2:
                c = trotter_circuit(cirq, rng, rng.randint(150, 260))
            else:
                c = moment_runs_circuit(
                    cirq, rng, rng.randint(40, 70), phases=rng.random() < 0.5
                )
            return (
                "merge_single_qubit_moments_to_phxz",
                c,
                lambda: cirq.merge_single_qubit_moments_to_phxz(c),
            )
        case "F3":
            kind = ("pxz", "unitary", "deep_phxz", "deep_moments")[index % 4]
            if kind == "pxz":
                c = random_gate_circuit(cirq, rng, rng.randint(4000, 7000))
                return (
                    kind,
                    c,
                    lambda: cirq.merge_single_qubit_gates_to_phased_x_and_z(c),
                )
            if kind == "unitary":
                ops = one_qubit_circuit_ops(cirq, rng, rng.randint(200, 350))
                return kind, ops, lambda: [cirq.unitary(op) for op in ops]
            if kind == "deep_phxz":
                c = deep_circuit(cirq, rng, rng.randint(80, 140), phases=False)
                return (
                    kind,
                    c,
                    lambda: cirq.merge_single_qubit_gates_to_phxz(
                        c, context=ctx_ignore
                    ),
                )
            c = deep_circuit(cirq, rng, rng.randint(100, 180), phases=True)
            return (
                kind,
                c,
                lambda: cirq.merge_single_qubit_moments_to_phxz(c, context=ctx_ignore),
            )
    raise ValueError(family)
