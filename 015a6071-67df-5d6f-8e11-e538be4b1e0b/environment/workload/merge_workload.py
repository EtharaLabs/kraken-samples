"""Visible workload: time Cirq's single-qubit merge transformers on a trotter-like circuit.

Run it with:  python /app/workload/merge_workload.py

It builds a layered circuit (Y**0.3 rotations between CZ layers on a small grid),
puts it through the CZ gauge transformer with a fixed seed, and times
cirq.merge_single_qubit_gates_to_phxz and cirq.merge_single_qubit_moments_to_phxz
on it. It prints each time and a digest of each result's structure, which must not
change when the library gets faster.
"""

import hashlib
import itertools
import time

import numpy as np

import cirq

SEED = 20260801
CYCLES = 300

QUBITS_PER_LAYER = [
    [
        cirq.GridQubit(5, 9),
        cirq.GridQubit(6, 9),
        cirq.GridQubit(5, 10),
        cirq.GridQubit(6, 8),
    ],
    [
        cirq.GridQubit(8, 8),
        cirq.GridQubit(6, 9),
        cirq.GridQubit(7, 9),
        cirq.GridQubit(5, 10),
        cirq.GridQubit(6, 10),
        cirq.GridQubit(7, 8),
    ],
    [
        cirq.GridQubit(6, 9),
        cirq.GridQubit(7, 9),
        cirq.GridQubit(6, 10),
        cirq.GridQubit(7, 8),
    ],
    [
        cirq.GridQubit(5, 9),
        cirq.GridQubit(6, 9),
        cirq.GridQubit(6, 8),
        cirq.GridQubit(7, 8),
    ],
]
CZ_PAIRS_PER_LAYER = [
    [
        (cirq.GridQubit(5, 9), cirq.GridQubit(5, 10)),
        (cirq.GridQubit(6, 8), cirq.GridQubit(6, 9)),
    ],
    [
        (cirq.GridQubit(5, 10), cirq.GridQubit(6, 10)),
        (cirq.GridQubit(6, 9), cirq.GridQubit(7, 9)),
        (cirq.GridQubit(7, 8), cirq.GridQubit(8, 8)),
    ],
    [
        (cirq.GridQubit(6, 9), cirq.GridQubit(6, 10)),
        (cirq.GridQubit(7, 8), cirq.GridQubit(7, 9)),
    ],
    [
        (cirq.GridQubit(5, 9), cirq.GridQubit(6, 9)),
        (cirq.GridQubit(6, 8), cirq.GridQubit(7, 8)),
    ],
]


def trotter_circuit() -> cirq.Circuit:
    all_qubits = sorted(set(itertools.chain.from_iterable(QUBITS_PER_LAYER)))
    moments = []
    for pairs, qubits in zip(CZ_PAIRS_PER_LAYER, QUBITS_PER_LAYER):
        moments.append(cirq.Moment((cirq.Y**0.3)(q) for q in qubits))
        moments.append(cirq.Moment(cirq.CZ(*pair) for pair in pairs))
    circuit = cirq.Circuit.from_moments(*moments) * CYCLES + cirq.Moment(
        cirq.M(*all_qubits)
    )
    gauge = cirq.transformers.gauge_compiling.cz_gauge.CZGaugeTransformer
    return gauge(circuit, prng=np.random.default_rng(SEED))


def structure_digest(circuit: cirq.AbstractCircuit) -> str:
    """Moment count, and the qubits and gate type of every operation in each moment."""
    rows = [
        sorted(
            (tuple(str(q) for q in op.qubits), type(op.gate).__name__) for op in moment
        )
        for moment in circuit
    ]
    return hashlib.sha256(repr(rows).encode()).hexdigest()[:16]


def main() -> None:
    for transformer in (
        cirq.merge_single_qubit_gates_to_phxz,
        cirq.merge_single_qubit_moments_to_phxz,
    ):
        circuit = trotter_circuit()
        start = time.perf_counter()
        merged = transformer(circuit)
        elapsed = time.perf_counter() - start
        print(
            f"{transformer.__name__}: moments {len(circuit)} -> {len(merged)}, "
            f"seconds={elapsed:.3f}, structure={structure_digest(merged)}"
        )


if __name__ == "__main__":
    main()
