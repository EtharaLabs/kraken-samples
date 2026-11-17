# Copyright 2026 The Cirq Developers
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Unitaries of one-qubit and zero-qubit operations as plain Python numbers.

Merging long runs of single-qubit gates spends most of its time computing and multiplying
2x2 matrices. The helpers here compute the matrices of the common single-qubit gates in
closed form and multiply them as tuples of Python complex numbers, which avoids the
overhead of the `cirq.unitary` protocol and of small numpy arrays.

A one-qubit unitary is a tuple `(u00, u01, u10, u11)` of its row-major entries, and a
zero-qubit unitary is a single complex number. The results are exact, global phase
included.
"""

from __future__ import annotations

import cmath
import math
from collections.abc import Callable
from typing import TYPE_CHECKING, TypeAlias

from cirq import protocols
from cirq.ops import common_gates, gate_operation, global_phase_op, identity, pauli_gates
from cirq.ops import phased_x_gate, phased_x_z_gate

if TYPE_CHECKING:
    import cirq

Matrix2: TypeAlias = tuple[complex, complex, complex, complex]

IDENTITY_2: Matrix2 = (1 + 0j, 0j, 0j, 1 + 0j)

_SQRT_HALF = math.sqrt(0.5)


def _is_number(x: object) -> bool:
    return isinstance(x, (int, float))


def _eigen_weights(gate: cirq.EigenGate) -> tuple[complex, complex] | None:
    """Returns the phases of the 0 and 1 half-turn eigenspaces of an exponentiated gate."""
    t = gate.exponent
    if not _is_number(t):
        return None
    s = gate.global_shift
    # The same powers as `cirq.EigenGate._unitary_`, so integer half-turns stay exact.
    return 1j ** (2 * t * s), 1j ** (2 * t * (1 + s))


def _x_pow(gate: cirq.XPowGate) -> Matrix2 | None:
    w = _eigen_weights(gate)
    if w is None:
        return None
    c, d = (w[0] + w[1]) * 0.5, (w[0] - w[1]) * 0.5
    return c, d, d, c


def _y_pow(gate: cirq.YPowGate) -> Matrix2 | None:
    w = _eigen_weights(gate)
    if w is None:
        return None
    c, d = (w[0] + w[1]) * 0.5, (w[0] - w[1]) * 0.5
    return c, -1j * d, 1j * d, c


def _z_pow(gate: cirq.ZPowGate) -> Matrix2 | None:
    w = _eigen_weights(gate)
    if w is None:
        return None
    return w[0], 0j, 0j, w[1]


def _h_pow(gate: cirq.HPowGate) -> Matrix2 | None:
    w = _eigen_weights(gate)
    if w is None:
        return None
    c, r = (w[0] + w[1]) * 0.5, (w[0] - w[1]) * 0.5 * _SQRT_HALF
    return c + r, r, r, c - r


def _phased_x_pow(gate: cirq.PhasedXPowGate) -> Matrix2 | None:
    t, p = gate.exponent, gate.phase_exponent
    if not (_is_number(t) and _is_number(p)):
        return None
    shift = cmath.exp(1j * math.pi * gate.global_shift * t)
    w1 = 1j ** (2 * t)
    c, d = (1 + w1) * 0.5 * shift, (1 - w1) * 0.5 * shift
    e = 1j ** (2 * p)
    return c, d * e.conjugate(), d * e, c


def _phased_xz(gate: cirq.PhasedXZGate) -> Matrix2 | None:
    a, x, z = gate.axis_phase_exponent, gate.x_exponent, gate.z_exponent
    if not (_is_number(a) and _is_number(x) and _is_number(z)):
        return None
    # The same terms as `cirq.PhasedXZGate._unitary_`, without round-off at half-integer x.
    if x % 1 == 0.5:
        ucx = 0.5 + 0.5j * (-1) ** math.floor(x)
        usx = ucx.conjugate()
    else:
        cpxh = 1j**x
        ucx = cpxh * cpxh.real
        usx = -1j * cpxh * cpxh.imag
    return ucx, usx * 1j ** (-2 * a), usx * 1j ** (2 * (z + a)), ucx * 1j ** (2 * z)


def _identity(gate: cirq.IdentityGate) -> Matrix2 | None:
    return IDENTITY_2 if gate.num_qubits() == 1 else None


# Closed forms by exact gate type. Subclasses that are not listed take the protocol path, so
# a subclass overriding its unitary is never mistaken for its parent.
_CLOSED_FORMS: dict[type, Callable[[cirq.Gate], Matrix2 | None]] = {
    common_gates.XPowGate: _x_pow,
    common_gates.Rx: _x_pow,
    pauli_gates._PauliX: _x_pow,
    common_gates.YPowGate: _y_pow,
    common_gates.Ry: _y_pow,
    pauli_gates._PauliY: _y_pow,
    common_gates.ZPowGate: _z_pow,
    common_gates.Rz: _z_pow,
    pauli_gates._PauliZ: _z_pow,
    common_gates.HPowGate: _h_pow,
    phased_x_gate.PhasedXPowGate: _phased_x_pow,
    phased_x_z_gate.PhasedXZGate: _phased_xz,
    identity.IdentityGate: _identity,
}


def single_qubit_unitary(op: cirq.Operation) -> Matrix2 | complex | None:
    """Returns the unitary of an operation on at most one qubit as plain Python numbers.

    Args:
        op: The operation.

    Returns:
        The tuple `(u00, u01, u10, u11)` for a unitary operation on one qubit, the complex
        coefficient for a unitary operation on no qubits, and None for an operation without
        a unitary or one acting on more than one qubit or on a qid that is not a qubit.
    """
    qubits = op.qubits
    if len(qubits) > 1:
        return None
    if (not qubits or qubits[0].dimension == 2) and isinstance(
        op.untagged, gate_operation.GateOperation
    ):
        gate = op.gate
        closed_form = _CLOSED_FORMS.get(type(gate))
        if closed_form is not None:
            return closed_form(gate)
        if type(gate) is global_phase_op.GlobalPhaseGate:
            coefficient = gate.coefficient
            return complex(coefficient) if isinstance(coefficient, (int, float, complex)) else None
    u = protocols.unitary(op, None)
    if u is None:
        return None
    if u.shape == (2, 2):
        return complex(u[0, 0]), complex(u[0, 1]), complex(u[1, 0]), complex(u[1, 1])
    if u.shape == (1, 1):
        return complex(u[0, 0])
    return None


def multiply(a: Matrix2, b: Matrix2) -> Matrix2:
    """Returns the matrix product `a @ b` of two one-qubit unitaries."""
    a00, a01, a10, a11 = a
    b00, b01, b10, b11 = b
    return (
        a00 * b00 + a01 * b10,
        a00 * b01 + a01 * b11,
        a10 * b00 + a11 * b10,
        a10 * b01 + a11 * b11,
    )
