"""Visible workload: capture a long program of two- and three-qubit controlled gates.

Run it with:  python /app/workload/trace_workload.py

It enables program capture, builds a fixed, seeded gate list, and times how long
jax.make_jaxpr takes to trace it once in a fresh interpreter. It also prints a
digest of the captured program, which must not change when the library gets
faster.
"""

import hashlib
import random
import time

import jax

import pennylane as qp

N_GATES = 6000
SEED = 20261014
GATES = (("CNOT", 2, 0), ("CZ", 2, 0), ("CRX", 2, 1), ("Toffoli", 3, 0))


def gate_list():
    rng = random.Random(SEED)
    out = []
    for _ in range(N_GATES):
        name, n_wires, n_params = rng.choice(GATES)
        wires = rng.sample(range(6), n_wires)
        params = [round(rng.uniform(-3.0, 3.0), 4) for _ in range(n_params)]
        out.append((name, wires, params))
    return out


def main():
    qp.capture.enable()
    gates = gate_list()

    def circuit():
        for name, wires, params in gates:
            getattr(qp, name)(*params, wires=wires)

    start = time.perf_counter()
    jaxpr = jax.make_jaxpr(circuit)()
    elapsed = time.perf_counter() - start
    digest = hashlib.sha256(str(jaxpr).encode()).hexdigest()
    print(f"gates={N_GATES} equations={len(jaxpr.eqns)} trace_seconds={elapsed:.3f}")
    print(f"program_digest={digest}")


if __name__ == "__main__":
    main()
