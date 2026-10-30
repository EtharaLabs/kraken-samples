"""Hidden workload generators for the verifier.

Everything here is data first: a seed and a size produce a plain list of
operation specs, and a separate builder turns that list into a traced program.
Spec generation happens outside the timed region.
"""

from __future__ import annotations

import random

FAMILIES = ("cnot", "ctrl", "adj", "adjctrl")

WIRES = 8

TWO_QUBIT_CONTROLLED = (
    "CNOT",
    "CZ",
    "CY",
    "CH",
    "CRX",
    "CRY",
    "CRZ",
    "CRot",
    "ControlledPhaseShift",
)
THREE_QUBIT_CONTROLLED = ("Toffoli", "CSWAP", "CCZ")
CTRL_BASES = (
    "RX",
    "RY",
    "RZ",
    "Rot",
    "Hadamard",
    "PhaseShift",
    "SX",
    "PauliY",
    "IsingZZ",
)
ADJ_BASES = ("S", "T", "SX", "RX", "RY", "RZ", "Rot", "PhaseShift")
PLAIN = ("PauliX", "PauliZ", "Hadamard", "RX", "RZ", "S", "T")

N_PARAMS = {
    "RX": 1,
    "RY": 1,
    "RZ": 1,
    "Rot": 3,
    "PhaseShift": 1,
    "IsingZZ": 1,
    "CRX": 1,
    "CRY": 1,
    "CRZ": 1,
    "CRot": 3,
    "ControlledPhaseShift": 1,
}
N_WIRES = {
    "IsingZZ": 2,
    **{g: 2 for g in TWO_QUBIT_CONTROLLED},
    **{g: 3 for g in THREE_QUBIT_CONTROLLED},
}


def _angles(rng: random.Random, name: str) -> list[float]:
    return [round(rng.uniform(-3.1, 3.1), 6) for _ in range(N_PARAMS.get(name, 0))]


def _gate(
    rng: random.Random, names: tuple[str, ...], used: set[int] | None = None
) -> tuple:
    name = rng.choice(names)
    pool = [w for w in range(WIRES) if not used or w not in used]
    wires = rng.sample(pool, N_WIRES.get(name, 1))
    return ("gate", name, wires, _angles(rng, name))


def _controls(
    rng: random.Random, base: tuple, k_max: int = 3
) -> tuple[list[int], list[int]]:
    pool = [w for w in range(WIRES) if w not in base[2]]
    controls = rng.sample(pool, rng.randint(1, k_max))
    return controls, [rng.randint(0, 1) for _ in controls]


def family_op(rng: random.Random, family: str) -> tuple:
    match family:
        case "cnot":
            return _gate(rng, TWO_QUBIT_CONTROLLED * 2 + THREE_QUBIT_CONTROLLED)
        case "ctrl":
            base = _gate(rng, CTRL_BASES)
            controls, values = _controls(rng, base)
            return ("ctrl", base, controls, values)
        case "adj":
            return ("adj", _gate(rng, ADJ_BASES))
        case "adjctrl":
            base = _gate(rng, CTRL_BASES)
            controls, values = _controls(rng, base, 2)
            return ("adj", ("ctrl", base, controls, values))
        case _:
            raise ValueError(family)


def family_specs(family: str, n: int, seed: int) -> list[tuple]:
    rng = random.Random(f"{family}:{n}:{seed}")
    if family == "prod":
        # One qp.prod call over n factors: one removal of many traced operators at once.
        return [("prod", [_gate(rng, PLAIN) for _ in range(n)])]
    return [family_op(rng, family) for _ in range(n)]


def _stmt(rng: random.Random, depth: int) -> tuple:
    roll = rng.random()
    if depth < 2 and roll < 0.08:
        return (
            "for",
            rng.randint(1, 3),
            [_stmt(rng, depth + 1) for _ in range(rng.randint(1, 4))],
        )
    if depth < 2 and roll < 0.16:
        return (
            "cond",
            round(rng.uniform(-1, 1), 3),
            [_stmt(rng, depth + 1) for _ in range(rng.randint(1, 3))],
            [_stmt(rng, depth + 1) for _ in range(rng.randint(0, 3))],
        )
    if roll < 0.24:
        a, b = _gate(rng, CTRL_BASES), _gate(rng, PLAIN)
        controls, values = _controls(rng, a)
        return ("ooo_ctrl", a, b, controls, values)
    if roll < 0.30:
        return ("ooo_adj", _gate(rng, ADJ_BASES), _gate(rng, PLAIN), _gate(rng, PLAIN))
    if roll < 0.36:
        return ("prod", [_gate(rng, PLAIN) for _ in range(rng.randint(2, 3))])
    if roll < 0.40:
        return ("sum", [_gate(rng, PLAIN) for _ in range(2)])
    if roll < 0.44:
        return ("adj", ("prod", [_gate(rng, PLAIN) for _ in range(2)]))
    if roll < 0.50:
        return _gate(rng, PLAIN)
    return family_op(rng, rng.choice(FAMILIES))


def program_specs(seed: int, n_stmts: int = 60) -> list[tuple]:
    rng = random.Random(f"program:{seed}")
    return [_stmt(rng, 0) for _ in range(n_stmts)]


def build_op(qp, spec, index=None):
    kind = spec[0]
    match kind:
        case "gate":
            _, name, wires, params = spec
            if index is not None and params:
                params = [params[0] * index, *params[1:]]
            return getattr(qp, name)(*params, wires=wires)
        case "ctrl":
            _, base, controls, values = spec
            return qp.ctrl(build_op(qp, base, index), controls, control_values=values)
        case "adj":
            return qp.adjoint(build_op(qp, spec[1], index))
        case "prod":
            return qp.prod(*[build_op(qp, s, index) for s in spec[1]])
        case "sum":
            return qp.sum(*[build_op(qp, s, index) for s in spec[1]])
        case _:
            raise ValueError(kind)


def run_stmt(qp, spec, x, index=None):
    kind = spec[0]
    match kind:
        case "for":
            _, k, body = spec

            @qp.for_loop(k)
            def loop(i):
                for s in body:
                    run_stmt(qp, s, x, i)

            loop()
        case "cond":
            _, c, true_body, false_body = spec

            def true_fn():
                for s in true_body:
                    run_stmt(qp, s, x, index)

            def false_fn():
                for s in false_body:
                    run_stmt(qp, s, x, index)

            qp.cond(x > c, true_fn, false_fn)()
        case "ooo_ctrl":
            _, a, b, controls, values = spec
            op_a = build_op(qp, a, index)
            build_op(qp, b, index)
            qp.ctrl(op_a, controls, control_values=values)
        case "ooo_adj":
            _, a, b, c = spec
            op_a = build_op(qp, a, index)
            build_op(qp, b, index)
            build_op(qp, c, index)
            qp.adjoint(op_a)
        case _:
            build_op(qp, spec, index)


def family_program(qp, specs):
    def f():
        for spec in specs:
            build_op(qp, spec)

    return f


def mixed_program(qp, specs):
    def f(x):
        for spec in specs:
            run_stmt(qp, spec, x)

    return f
