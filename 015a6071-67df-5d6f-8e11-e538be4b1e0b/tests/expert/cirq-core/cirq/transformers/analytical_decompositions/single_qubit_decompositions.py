# Copyright 2018 The Cirq Developers
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

"""Utility methods related to optimizing quantum circuits."""

from __future__ import annotations

import cmath
import math

import numpy as np
import sympy

from cirq import linalg, ops
from cirq.linalg.tolerance import near_zero_mod


def is_negligible_turn(turns: float, tolerance: float) -> bool:
    """Returns True is the number of turns in a gate is close to zero."""
    if isinstance(turns, sympy.Expr):
        if not turns.is_constant():
            return False
        turns = float(turns)
    return abs(_signed_mod_1(turns)) <= tolerance


def _signed_mod_1(x: float) -> float:
    return (x + 0.5) % 1 - 0.5


def single_qubit_matrix_to_pauli_rotations(
    mat: np.ndarray, atol: float = 0
) -> list[tuple[ops.Pauli, float]]:
    """Implements a single-qubit operation with few rotations.

    Args:
        mat: The 2x2 unitary matrix of the operation to implement.
        atol: A limit on the amount of absolute error introduced by the
            construction.

    Returns:
        A list of (Pauli, half_turns) tuples that, when applied in order,
        perform the desired operation.
    """

    def is_clifford_rotation(half_turns):
        return near_zero_mod(half_turns, 0.5, atol=atol)

    def to_quarter_turns(half_turns):
        return round(2 * half_turns) % 4

    def is_quarter_turn(half_turns):
        return is_clifford_rotation(half_turns) and to_quarter_turns(half_turns) % 2 == 1

    def is_half_turn(half_turns):
        return is_clifford_rotation(half_turns) and to_quarter_turns(half_turns) == 2

    def is_no_turn(half_turns):
        return is_clifford_rotation(half_turns) and to_quarter_turns(half_turns) == 0

    # Decompose matrix
    z_rad_before, y_rad, z_rad_after = linalg.deconstruct_single_qubit_matrix_into_angles(mat)
    z_ht_before = z_rad_before / np.pi - 0.5
    m_ht = y_rad / np.pi
    m_pauli: ops.Pauli = ops.X
    z_ht_after = z_rad_after / np.pi + 0.5

    # Clean up angles
    if is_clifford_rotation(z_ht_before):
        if (is_quarter_turn(z_ht_before) or is_quarter_turn(z_ht_after)) ^ (
            is_half_turn(m_ht) and is_no_turn(z_ht_before - z_ht_after)
        ):
            z_ht_before += 0.5
            z_ht_after -= 0.5
            m_pauli = ops.Y
        if is_half_turn(z_ht_before) or is_half_turn(z_ht_after):
            z_ht_before -= 1
            z_ht_after += 1
            m_ht = -m_ht
    if is_no_turn(m_ht):
        z_ht_before += z_ht_after
        z_ht_after = 0
    elif is_half_turn(m_ht):
        z_ht_after -= z_ht_before
        z_ht_before = 0

    # Generate operations
    rotation_list = [(ops.Z, z_ht_before), (m_pauli, m_ht), (ops.Z, z_ht_after)]
    return [(pauli, ht) for pauli, ht in rotation_list if not is_no_turn(ht)]


def single_qubit_matrix_to_gates(mat: np.ndarray, tolerance: float = 0) -> list[ops.Gate]:
    """Implements a single-qubit operation with few gates.

    Args:
        mat: The 2x2 unitary matrix of the operation to implement.
        tolerance: A limit on the amount of error introduced by the
            construction.

    Returns:
        A list of gates that, when applied in order, perform the desired
            operation.
    """
    rotations = single_qubit_matrix_to_pauli_rotations(mat, tolerance)
    return [pauli**ht for pauli, ht in rotations]


def single_qubit_op_to_framed_phase_form(mat: np.ndarray) -> tuple[np.ndarray, complex, complex]:
    """Decomposes a 2x2 unitary M into U^-1 * diag(1, r) * U * diag(g, g).

    U translates the rotation axis of M to the Z axis.
    g fixes a global phase factor difference caused by the translation.
    r's phase is the amount of rotation around M's rotation axis.

    This decomposition can be used to decompose controlled single-qubit
    rotations into controlled-Z operations bordered by single-qubit operations.

    Args:
      mat:  The qubit operation as a 2x2 unitary matrix.

    Returns:
        A 2x2 unitary U, the complex relative phase factor r, and the complex
        global phase factor g. Applying M is equivalent (up to global phase) to
        applying U, rotating around the Z axis to apply r, then un-applying U.
        When M is controlled, the control must be rotated around the Z axis to
        apply g.
    """
    vals, vecs = linalg.unitary_eig(mat)
    u = np.conj(vecs).T
    r = vals[1] / vals[0]
    g = vals[0]
    return u, r, g


def _deconstruct_single_qubit_matrix_into_gate_turns(mat: np.ndarray) -> tuple[float, float, float]:
    """Breaks down a 2x2 unitary into gate parameters.

    The angles are those of `cirq.deconstruct_single_qubit_matrix_into_angles`, computed step by
    step on the four entries of the matrix as Python complex numbers rather than with 2x2 numpy
    products, which dominate the cost for a single small matrix.

    Args:
        mat: The 2x2 unitary matrix to break down.

    Returns:
       A tuple containing the amount to rotate around an XY axis, the phase of
       that axis, and the amount to phase around Z. All results will be in
       fractions of a whole turn, with values canonicalized into the range
       [-0.5, 0.5).
    """
    (u00, u01), (u10, u11) = np.asarray(mat).tolist()
    # Adding 0j turns a signed zero into +0, as the 2x2 numpy products of the base do; the
    # phase of an exact zero entry then matches `cirq.deconstruct_single_qubit_matrix_into_angles`.
    u00, u01, u10, u11 = u00 + 0j, u01 + 0j, u10 + 0j, u11 + 0j

    # Anti-cancel left-vs-right phase along top row.
    right_phase = cmath.phase(u01 * u00.conjugate()) + math.pi
    right = cmath.exp(-1j * right_phase)
    u01 *= right
    u11 *= right

    # Cancel top-vs-bottom phase along left column.
    bottom_phase = cmath.phase(u10 * u00.conjugate())
    bottom = cmath.exp(-1j * bottom_phase)
    u10 *= bottom
    u11 *= bottom

    # Lined up for a rotation. Clear the off-diagonal cells with one.
    rotation = math.atan2(abs(u10), abs(u00))
    c, s = math.cos(rotation), math.sin(rotation)

    # Cancel top-left-vs-bottom-right phase.
    diagonal_phase = cmath.phase((c * u11 - s * u01) * (c * u00 + s * u10).conjugate())
    pre_phase, post_phase = right_phase + diagonal_phase, bottom_phase

    # Figure out parameters of the actual gates we will do.
    tau = 2 * np.pi
    xy_turn = rotation / math.pi
    xy_phase_turn = 0.25 - pre_phase / tau
    total_z_turn = (post_phase + pre_phase) / tau

    # Normalize turns into the range [-0.5, 0.5).
    return (_signed_mod_1(xy_turn), _signed_mod_1(xy_phase_turn), _signed_mod_1(total_z_turn))


def single_qubit_matrix_to_phased_x_z(mat: np.ndarray, atol: float = 0) -> list[ops.Gate]:
    """Implements a single-qubit operation with a PhasedX and Z gate.

    If one of the gates isn't needed, it will be omitted.

    Args:
        mat: The 2x2 unitary matrix of the operation to implement.
        atol: A limit on the amount of error introduced by the
            construction.

    Returns:
        A list of gates that, when applied in order, perform the desired
            operation.
    """

    xy_turn, xy_phase_turn, total_z_turn = _deconstruct_single_qubit_matrix_into_gate_turns(mat)

    # Keep the non-negligible XY and Z rotations. The trace distance bounds are the ones
    # `cirq.trace_distance_bound` gives for `cirq.PhasedXPowGate(exponent=2 * xy_turn)` and
    # `cirq.Z ** (2 * total_z_turn)`, in closed form.
    keep_xy = abs(math.sin(xy_turn * math.pi)) > atol
    keep_z = _z_pow_trace_distance_bound(2 * total_z_turn) > atol

    # Special case: XY half-turns can absorb Z rotations.
    if keep_xy and keep_z and math.isclose(abs(xy_turn), 0.5, abs_tol=atol):
        return [ops.PhasedXPowGate(phase_exponent=2 * xy_phase_turn + total_z_turn)]

    result: list[ops.Gate] = []
    if keep_xy:
        result.append(ops.PhasedXPowGate(exponent=2 * xy_turn, phase_exponent=2 * xy_phase_turn))
    if keep_z:
        result.append(ops.Z ** (2 * total_z_turn))
    return result


def _z_pow_trace_distance_bound(exponent: float) -> float:
    """The trace distance bound of `cirq.Z**exponent`, from the gap between its eigenphases."""
    gap = math.pi * (exponent % 2)
    widest = max(2 * math.pi - gap, gap)
    return 1.0 if widest <= math.pi else max(0.0, math.sin(0.5 * widest))


def single_qubit_matrix_to_phxz(mat: np.ndarray, atol: float = 0) -> ops.PhasedXZGate | None:
    """Implements a single-qubit operation with a PhasedXZ gate.

    Under the hood, this computes the angles of deconstruct_single_qubit_matrix_into_angles,
    which converts the given matrix to a series of three rotations around the Z, Y, Z
    axes. This is then converted to a phased X rotation followed by a Z, in the
    form of a single PhasedXZ gate.

    Args:
        mat: The 2x2 unitary matrix of the operation to implement.
        atol: A limit on the amount of error introduced by the
            construction.

    Returns:
        A PhasedXZ gate that implements the given matrix, or None if it is
        close to identity (trace distance <= atol).
    """

    xy_turn, xy_phase_turn, total_z_turn = _deconstruct_single_qubit_matrix_into_gate_turns(mat)

    # The trace distance of PhasedXZGate(a, x, z) from the identity, in closed form, is
    # sqrt(sin^2(pi x / 2) + cos^2(pi x / 2) sin^2(pi z / 2)), here with x = 2 * xy_turn and
    # z = 2 * total_z_turn.
    x_sin, x_cos = math.sin(xy_turn * math.pi), math.cos(xy_turn * math.pi)
    z_sin = math.sin(total_z_turn * math.pi)
    if math.sqrt(x_sin * x_sin + x_cos * x_cos * z_sin * z_sin) <= atol:
        return None

    # Special case: XY half-turns can absorb Z rotations.
    if math.isclose(abs(xy_turn), 0.5, abs_tol=atol):
        return ops.PhasedXZGate(
            axis_phase_exponent=2 * xy_phase_turn + total_z_turn, x_exponent=1, z_exponent=0
        )

    return ops.PhasedXZGate(
        axis_phase_exponent=2 * xy_phase_turn, x_exponent=2 * xy_turn, z_exponent=2 * total_z_turn
    )
