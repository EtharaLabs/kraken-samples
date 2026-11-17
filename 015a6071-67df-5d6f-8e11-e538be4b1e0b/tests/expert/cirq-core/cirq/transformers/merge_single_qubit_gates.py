# Copyright 2022 The Cirq Developers
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

"""Transformer passes to combine adjacent single-qubit rotations."""

from __future__ import annotations

import cmath
import math
from collections.abc import Callable, Hashable
from typing import cast, TYPE_CHECKING

import numpy as np

from cirq import circuits, ops, protocols
from cirq.circuits.circuit import CIRCUIT_TYPE
from cirq.ops import single_qubit_unitary
from cirq.study.resolver import ParamResolver
from cirq.study.sweeps import dict_to_zip_sweep, ListSweep, ProductOrZipSweepLike, Sweep, Zip
from cirq.transformers import (
    align,
    merge_k_qubit_gates,
    symbolize,
    tag_transformers,
    transformer_api,
    transformer_primitives,
)
from cirq.transformers.analytical_decompositions import single_qubit_decompositions

if TYPE_CHECKING:
    import sympy

    import cirq

_Matrix2 = single_qubit_unitary.Matrix2


def _signed_mod_1(x: float) -> float:
    return (x + 0.5) % 1 - 0.5


def _gate_turns(u: _Matrix2) -> tuple[float, float, float]:
    """Breaks down a 2x2 unitary into XY-rotation, XY-axis phase and Z turns.

    Follows `cirq.deconstruct_single_qubit_matrix_into_angles` step by step on plain complex
    numbers, then converts the angles to fractions of a turn in [-0.5, 0.5) as
    `cirq.single_qubit_matrix_to_phxz` does.
    """
    u00, u01, u10, u11 = u
    # Anti-cancel left-vs-right phase along the top row.
    right_phase = cmath.phase(u01 * u00.conjugate()) + math.pi
    r = cmath.exp(-1j * right_phase)
    u11 *= r
    # Cancel top-vs-bottom phase along the left column.
    bottom_phase = cmath.phase(u10 * u00.conjugate())
    b = cmath.exp(-1j * bottom_phase)
    u10 *= b
    u11 *= b
    # Clear the off-diagonal cells with a rotation.
    rotation = math.atan2(abs(u10), abs(u00))
    c, s = math.cos(rotation), math.sin(rotation)
    d00 = c * u00 + s * u10
    d11 = -s * u01 * r + c * u11
    # Cancel top-left-vs-bottom-right phase.
    diagonal_phase = cmath.phase(d11 * d00.conjugate())
    pre_phase, post_phase = right_phase + diagonal_phase, bottom_phase
    tau = 2 * math.pi
    return (
        _signed_mod_1(2 * rotation / tau),
        _signed_mod_1(0.25 - pre_phase / tau),
        _signed_mod_1((post_phase + pre_phase) / tau),
    )


def _matrix_to_phxz(u: _Matrix2, atol: float) -> cirq.PhasedXZGate | None:
    """`cirq.single_qubit_matrix_to_phxz` for a unitary given as a tuple of its entries."""
    xy_turn, xy_phase_turn, total_z_turn = _gate_turns(u)
    # Trace distance of PhasedXZ(a, x, z) from the identity in closed form, with x = 2 xy_turn
    # and z = 2 total_z_turn: sqrt(sin^2(pi x / 2) + cos^2(pi x / 2) sin^2(pi z / 2)).
    sx, cx, sz = (
        math.sin(math.pi * xy_turn),
        math.cos(math.pi * xy_turn),
        math.sin(math.pi * total_z_turn),
    )
    if math.sqrt(sx * sx + cx * cx * sz * sz) <= atol:
        return None
    # XY half-turns can absorb Z rotations.
    if math.isclose(abs(xy_turn), 0.5, abs_tol=atol):
        return ops.PhasedXZGate(
            axis_phase_exponent=2 * xy_phase_turn + total_z_turn, x_exponent=1, z_exponent=0
        )
    return ops.PhasedXZGate(
        axis_phase_exponent=2 * xy_phase_turn, x_exponent=2 * xy_turn, z_exponent=2 * total_z_turn
    )


def _eigen_trace_distance(exponent: float) -> float:
    """Trace distance bound of an exponentiated gate with eigen shifts 0 and 1."""
    gap = math.pi * (exponent % 2)
    widest = max(2 * math.pi - gap, gap)
    return 1.0 if widest <= math.pi else max(0.0, math.sin(0.5 * widest))


def _matrix_to_phased_x_z(u: _Matrix2, atol: float) -> list[cirq.Gate]:
    """`cirq.single_qubit_matrix_to_phased_x_z` for a unitary given as a tuple of its entries."""
    xy_turn, xy_phase_turn, total_z_turn = _gate_turns(u)
    keep_x = abs(math.sin(2 * xy_turn * 0.5 * math.pi)) > atol
    keep_z = _eigen_trace_distance(2 * total_z_turn) > atol
    # XY half-turns can absorb Z rotations.
    if keep_x and keep_z and math.isclose(abs(xy_turn), 0.5, abs_tol=atol):
        return [ops.PhasedXPowGate(phase_exponent=2 * xy_phase_turn + total_z_turn)]
    result: list[cirq.Gate] = []
    if keep_x:
        result.append(ops.PhasedXPowGate(exponent=2 * xy_turn, phase_exponent=2 * xy_phase_turn))
    if keep_z:
        result.append(ops.Z ** (2 * total_z_turn))
    return result


def _run_unitary(circuit_op: cirq.CircuitOperation) -> _Matrix2 | complex:
    """Returns the unitary of a merged run of operations acting on at most one qubit."""
    u: _Matrix2 | complex | None = None
    for op in circuit_op.circuit.all_operations():
        op_u = single_qubit_unitary.single_qubit_unitary(op)
        if op_u is None:
            break
        if u is None:
            u = op_u
        elif isinstance(op_u, complex) and isinstance(u, complex):
            u *= op_u
        elif isinstance(op_u, complex) or isinstance(u, complex):
            break
        else:
            u = single_qubit_unitary.multiply(op_u, u)
    else:
        if u is not None:
            return u
    mat = protocols.unitary(circuit_op)
    if mat.shape == (1, 1):
        return complex(mat[0, 0])
    return complex(mat[0, 0]), complex(mat[0, 1]), complex(mat[1, 0]), complex(mat[1, 1])


def _merge_single_qubit_runs(
    circuit: cirq.AbstractCircuit,
    rewriter: Callable[[cirq.Qid, np.ndarray, list[cirq.Operation]], cirq.Operation],
    tags_to_ignore: frozenset[Hashable],
) -> cirq.Circuit:
    """Replaces every run of single-qubit unitaries in `circuit` with one operation.

    This gives the circuit of `cirq.merge_k_qubit_unitaries` with `k=1` and a rewriter producing
    one operation per run, for a circuit whose circuit operations are not recursed into, without
    building connected components or wrapping each run in a `cirq.CircuitOperation`. An operation
    is mergeable if it is a unitary acting on at most one qubit and carries none of
    `tags_to_ignore`. A run is a maximal sequence of mergeable operations on one qubit with no
    other operation on that qubit in between; its unitary is accumulated while the operations are
    visited, as a tuple of Python complex numbers (a numpy array on a qid that is not a qubit).
    Each run is replaced, in the moment of its first operation, by
    `rewriter(qubit, unitary, operations)`, and each mergeable operation on no qubits by a
    `cirq.GlobalPhaseGate`. Moments left empty are dropped.
    """
    new_ops_by_moment: list[list[cirq.Operation]] = []
    runs_by_moment: list[list[list]] = []
    # The open run on each qubit, as [qubit, unitary so far, operations].
    open_runs: dict[cirq.Qid, list] = {}
    for moment in circuit:
        new_ops: list[cirq.Operation] = []
        started: list[list] = []
        for op in moment:
            u = None
            if tags_to_ignore.isdisjoint(op.tags):
                u = single_qubit_unitary.single_qubit_unitary(op)
                if u is None and len(op.qubits) == 1:
                    # `single_qubit_unitary` leaves out unitaries on qids that are not qubits.
                    u = protocols.unitary(op, None)
            if u is not None:
                qubits = op.qubits
                if not qubits:
                    new_ops.append(ops.GlobalPhaseGate(cast(complex, u)).on())
                    continue
                run = open_runs.get(qubits[0])
                if run is None:
                    run = open_runs[qubits[0]] = [qubits[0], u, [op]]
                    started.append(run)
                else:
                    if isinstance(u, tuple):
                        run[1] = single_qubit_unitary.multiply(u, run[1])
                    else:
                        run[1] = u @ run[1]
                    run[2].append(op)
                continue
            # The operation is kept as it is and ends the runs on its qubits.
            new_ops.append(op)
            for q in op.qubits:
                open_runs.pop(q, None)
        new_ops_by_moment.append(new_ops)
        runs_by_moment.append(started)

    moments = []
    for new_ops, started in zip(new_ops_by_moment, runs_by_moment):
        for q, u, run_ops in started:
            mat = np.array(((u[0], u[1]), (u[2], u[3]))) if isinstance(u, tuple) else u
            new_ops.append(rewriter(q, mat, run_ops))
        if new_ops:
            moments.append(circuits.Moment.from_ops(*new_ops))
    return circuits.Circuit.from_moments(*moments)


@transformer_api.transformer
def merge_single_qubit_gates_to_phased_x_and_z(
    circuit: cirq.AbstractCircuit,
    *,
    context: cirq.TransformerContext | None = None,
    atol: float = 1e-8,
) -> cirq.Circuit:
    """Replaces runs of single qubit rotations with `cirq.PhasedXPowGate` and `cirq.ZPowGate`.

    Specifically, any run of non-parameterized single-qubit unitaries will be replaced by an
    optional PhasedX operation followed by an optional Z operation.

    Args:
        circuit: Input circuit to transform. It will not be modified.
        context: `cirq.TransformerContext` storing common configurable options for transformers.
        atol: Absolute tolerance to angle error. Larger values allow more negligible gates to be
            dropped, smaller values increase accuracy.

    Returns:
        Copy of the transformed input circuit.
    """

    def rewriter(op: cirq.CircuitOperation) -> cirq.OP_TREE:
        u = _run_unitary(op)
        if isinstance(u, complex):
            return ops.GlobalPhaseGate(u).on()
        (q,) = op.circuit.all_qubits()
        return [g(q) for g in _matrix_to_phased_x_z(u, atol)]

    return merge_k_qubit_gates.merge_k_qubit_unitaries(
        circuit, k=1, context=context, rewriter=rewriter
    )


@transformer_api.transformer
def merge_single_qubit_gates_to_phxz(
    circuit: cirq.AbstractCircuit,
    *,
    context: cirq.TransformerContext | None = None,
    merge_tags_fn: Callable[[cirq.CircuitOperation], list[Hashable]] | None = None,
    atol: float = 1e-8,
) -> cirq.Circuit:
    """Replaces runs of single qubit rotations with a single optional `cirq.PhasedXZGate`.

    Specifically, any run of non-parameterized single-qubit unitaries will be replaced by an
    optional PhasedXZ.

    Args:
        circuit: Input circuit to transform. It will not be modified.
        context: `cirq.TransformerContext` storing common configurable options for transformers.
        merge_tags_fn: A callable returns the tags to be added to the merged operation.
        atol: Absolute tolerance to angle error. Larger values allow more negligible gates to be
            dropped, smaller values increase accuracy.

    Returns:
        Copy of the transformed input circuit.
    """

    def rewrite_run(
        q: cirq.Qid, mat: np.ndarray, run_ops: list[cirq.Operation]
    ) -> cirq.Operation:
        gate = single_qubit_decompositions.single_qubit_matrix_to_phxz(mat, atol) or ops.I
        phxz_op = gate.on(q)
        if merge_tags_fn:
            circuit_op = circuits.CircuitOperation(circuits.FrozenCircuit(run_ops))
            return phxz_op.with_tags(*merge_tags_fn(circuit_op))
        return phxz_op

    if not (context and context.deep):
        return _merge_single_qubit_runs(
            circuit, rewrite_run, frozenset(context.tags_to_ignore) if context else frozenset()
        )

    # Runs inside circuit operations are merged by `cirq.merge_k_qubit_unitaries`.
    def rewriter(circuit_op: cirq.CircuitOperation) -> cirq.OP_TREE:
        u = _run_unitary(circuit_op)
        if isinstance(u, complex):
            return ops.GlobalPhaseGate(u).on()
        (q,) = circuit_op.circuit.all_qubits()
        mat = np.array(((u[0], u[1]), (u[2], u[3])))
        return rewrite_run(q, mat, list(circuit_op.circuit.all_operations()))

    return merge_k_qubit_gates.merge_k_qubit_unitaries(
        circuit, k=1, context=context, rewriter=rewriter
    )


def _merge_moment_runs(
    circuit: CIRCUIT_TYPE,
    atol: float,
    tags_to_ignore: frozenset[Hashable],
    deep: bool,
    tags_to_skip: frozenset[Hashable],
) -> CIRCUIT_TYPE:
    """Merges every run of two or more mergeable moments of `circuit` into one moment.

    A moment is mergeable when each of its operations is a unitary on at most one qubit (a qid
    of dimension 2; an operation on a qid of any other dimension is not mergeable) not tagged
    with `tags_to_ignore`. A run of a single mergeable moment is kept as it is. If `deep`,
    circuit operations not tagged with `tags_to_skip`
    are first processed recursively, and circuits nested within them are processed without
    skipping any.
    """
    moments: list[cirq.Moment] = []
    run: list[cirq.Moment] = []
    by_qubit: dict[cirq.Qid, list] = {}
    phase_ops: list[cirq.Operation] = []
    phase = 1 + 0j

    def flush() -> None:
        nonlocal phase
        if len(run) == 1:
            moments.append(run[0])
        elif run:
            merged_ops: list[cirq.Operation] = []
            for q, (first_op, count, u) in by_qubit.items():
                if count == 1 and isinstance(first_op.gate, ops.PhasedXZGate):
                    merged_ops.append(first_op)
                    continue
                gate = _matrix_to_phxz(u, atol)
                if gate:
                    merged_ops.append(gate.on(q))
            if len(phase_ops) == 1:
                merged_ops.append(phase_ops[0])
            elif phase_ops:
                merged_ops.append(ops.GlobalPhaseGate(phase).on())
            moments.append(circuits.Moment.from_ops(*merged_ops))
        run.clear()
        by_qubit.clear()
        phase_ops.clear()
        phase = 1 + 0j

    for moment in circuit:
        if deep:
            moment = _merge_moment_runs_in_circuit_ops(moment, atol, tags_to_ignore, tags_to_skip)
        entries = []
        for op in moment:
            if not (
                protocols.num_qubits(op) <= 1
                and protocols.has_unitary(op)
                and tags_to_ignore.isdisjoint(op.tags)
            ):
                break
            u = single_qubit_unitary.single_qubit_unitary(op)
            if u is None:
                break
            entries.append((op, u))
        else:
            run.append(moment)
            for op, u in entries:
                if isinstance(u, complex):
                    phase_ops.append(op)
                    phase *= u
                    continue
                q = op.qubits[0]
                acc = by_qubit.get(q)
                if acc is None:
                    by_qubit[q] = [op, 1, u]
                else:
                    acc[1] += 1
                    acc[2] = single_qubit_unitary.multiply(u, acc[2])
            continue
        flush()
        moments.append(moment)
    flush()
    if isinstance(circuit, circuits.FrozenCircuit):
        return cast(CIRCUIT_TYPE, circuits.FrozenCircuit.from_moments(*moments, tags=circuit.tags))
    return cast(CIRCUIT_TYPE, circuits.Circuit.from_moments(*moments))


def _merge_moment_runs_in_circuit_ops(
    moment: cirq.Moment,
    atol: float,
    tags_to_ignore: frozenset[Hashable],
    tags_to_skip: frozenset[Hashable],
) -> cirq.Moment:
    """Applies `_merge_moment_runs` to the circuits of the circuit operations in `moment`."""
    if not any(isinstance(op.untagged, circuits.CircuitOperation) for op in moment):
        return moment
    new_ops: list[cirq.Operation] = []
    for op in moment:
        op_untagged = op.untagged
        if isinstance(op_untagged, circuits.CircuitOperation) and tags_to_skip.isdisjoint(op.tags):
            op = op_untagged.replace(
                circuit=_merge_moment_runs(
                    op_untagged.circuit, atol, tags_to_ignore, True, frozenset()
                )
            ).with_tags(*op.tags)
        new_ops.append(op)
    return circuits.Moment.from_ops(*new_ops)


@transformer_api.transformer
def merge_single_qubit_moments_to_phxz(
    circuit: cirq.AbstractCircuit,
    *,
    context: cirq.TransformerContext | None = None,
    atol: float = 1e-8,
) -> cirq.Circuit:
    """Merges adjacent moments with only 1-qubit rotations to a single moment with PhasedXZ gates.

    Each run of two or more consecutive mergeable moments is merged in one step (a single
    mergeable moment is kept as it is): the unitaries acting on each
    qubit are multiplied together as 2x2 matrices of Python complex numbers and decomposed into a
    single PhasedXZ gate, which is dropped if it is the identity within `atol`; a qubit with a
    single PhasedXZ operation in the run keeps that operation. The global phase operations of the
    run are combined into a single `cirq.GlobalPhaseGate` (a single one is kept as it is).

    Args:
        circuit: Input circuit to transform. It will not be modified.
        context: `cirq.TransformerContext` storing common configurable options for transformers.
        atol: Absolute tolerance to angle error. Larger values allow more negligible gates to be
            dropped, smaller values increase accuracy.

    Returns:
        Copy of the transformed input circuit.
    """
    tags_to_ignore = frozenset(context.tags_to_ignore) if context else frozenset()
    return _merge_moment_runs(
        circuit, atol, tags_to_ignore, context.deep if context else False, tags_to_ignore
    ).unfreeze(copy=False)


def _sweep_on_symbols(sweep: Sweep, symbols: set[sympy.Symbol]) -> Sweep:
    new_resolvers: list[cirq.ParamResolver] = []
    for resolver in sweep:
        param_dict: cirq.ParamMappingType = {s: resolver.value_of(s) for s in symbols}
        new_resolvers.append(ParamResolver(param_dict))
    return ListSweep(new_resolvers)


def _calc_phxz_sweeps(
    symbolized_circuit: cirq.Circuit, resolved_circuits: list[cirq.Circuit]
) -> Sweep:
    """Returns the phxz sweep of the symbolized_circuit on resolved_circuits.

    Raises:
        ValueError: Structural mismatch: A `resolved_circuit` contains an unexpected gate type.
            Expected a `PhasedXZGate` or `IdentityGate` at a position corresponding to a
            symbolic `PhasedXZGate` in the `symbolized_circuit`.
    """

    def _extract_axz(op: ops.Operation | None) -> tuple[float, float, float]:
        if not op or not op.gate or not isinstance(op.gate, ops.IdentityGate | ops.PhasedXZGate):
            raise ValueError(f"Expect a PhasedXZGate or IdentityGate on op {op}.")
        if isinstance(op.gate, ops.IdentityGate):
            return 0.0, 0.0, 0.0  # Identity gate's a, x, z in PhasedXZ
        return op.gate.axis_phase_exponent, op.gate.x_exponent, op.gate.z_exponent

    values_by_params: dict[sympy.Symbol, tuple[float, ...]] = {}
    for mid, moment in enumerate(symbolized_circuit):
        for op in moment.operations:
            if op.gate and isinstance(op.gate, ops.PhasedXZGate) and protocols.is_parameterized(op):
                sa, sx, sz = op.gate.axis_phase_exponent, op.gate.x_exponent, op.gate.z_exponent
                values_by_params[sa], values_by_params[sx], values_by_params[sz] = zip(
                    *[_extract_axz(c[mid].operation_at(op.qubits[0])) for c in resolved_circuits]
                )

    return dict_to_zip_sweep(cast(ProductOrZipSweepLike, values_by_params))


def merge_single_qubit_gates_to_phxz_symbolized(
    circuit: cirq.AbstractCircuit,
    *,
    context: cirq.TransformerContext | None = None,
    sweep: Sweep,
    atol: float = 1e-8,
) -> tuple[cirq.Circuit, Sweep]:
    """Merges consecutive single qubit gates as PhasedXZ Gates. Symbolizes if any of
      the consecutive gates is symbolized.

    Example:
        >>> q0, q1 = cirq.LineQubit.range(2)
        >>> c = cirq.Circuit(\
                    cirq.X(q0),\
                    cirq.CZ(q0,q1)**sympy.Symbol("cz_exp"),\
                    cirq.Y(q0)**sympy.Symbol("y_exp"),\
                    cirq.X(q0))
        >>> print(c)
        0: ───X───@──────────Y^y_exp───X───
                  │
        1: ───────@^cz_exp─────────────────
        >>> new_circuit, new_sweep = cirq.merge_single_qubit_gates_to_phxz_symbolized(\
                c, sweep=cirq.Zip(cirq.Points(key="cz_exp", points=[0, 1]),\
                                  cirq.Points(key="y_exp",  points=[0, 1])))
        >>> print(new_circuit)
        0: ───PhXZ(a=-1,x=1,z=0)───@──────────PhXZ(a=a0,x=x0,z=z0)───
                                   │
        1: ────────────────────────@^cz_exp──────────────────────────
        >>> assert new_sweep[0] == cirq.ParamResolver({'a0': -1, 'x0': 1, 'z0': 0, 'cz_exp': 0})
        >>> assert new_sweep[1] == cirq.ParamResolver({'a0': -0.5, 'x0': 0, 'z0': -1, 'cz_exp': 1})

    Args:
        circuit: Input circuit to transform. It will not be modified.
        context: `cirq.TransformerContext` storing common configurable options for transformers.
        sweep: Sweep of the symbols in the input circuit. An updated Sweep will be returned
            based on the transformation.
        atol: Absolute tolerance to angle error. Larger values allow more negligible gates to be
            dropped, smaller values increase accuracy.

    Returns:
        Copy of the transformed input circuit.
    """
    deep = context.deep if context else False

    # Tag symbolized single-qubit op.
    symbolized_single_tag = "_tmp_symbolize_tag"

    circuit_tagged = transformer_primitives.map_operations(
        circuit,
        lambda op, _: (
            op.with_tags(symbolized_single_tag)
            if protocols.is_parameterized(op) and len(op.qubits) == 1
            else op
        ),
        deep=deep,
    )

    # Step 0, isolate single qubit symbols and resolve the circuit on them.
    single_qubit_gate_symbols: set[sympy.Symbol] = set().union(
        *[
            protocols.parameter_symbols(op) if symbolized_single_tag in op.tags else set()
            for op in circuit_tagged.all_operations()
        ]
    )
    # Remaining symbols, e.g., 2 qubit gates' symbols. Sweep of those symbols keeps unchanged.
    remaining_symbols: set[sympy.Symbol] = set(
        protocols.parameter_symbols(circuit) - single_qubit_gate_symbols
    )
    # If all single qubit gates are not parameterized, call the non-parameterized version of
    # the transformer.
    if not single_qubit_gate_symbols:
        return (merge_single_qubit_gates_to_phxz(circuit, context=context, atol=atol), sweep)
    sweep_of_single: Sweep = _sweep_on_symbols(sweep, single_qubit_gate_symbols)
    # Get all resolved circuits from all sets of resolvers in sweep_of_single.
    resolved_circuits = [
        protocols.resolve_parameters(circuit_tagged, resolver) for resolver in sweep_of_single
    ]

    # Step 1, merge single qubit gates per resolved circuit, preserving
    #  the symbolized_single_tag to indicate the operator is a merged one.
    merged_circuits: list[cirq.Circuit] = [
        merge_single_qubit_gates_to_phxz(
            c,
            context=context,
            merge_tags_fn=lambda circuit_op: (
                [symbolized_single_tag]
                if any(
                    symbolized_single_tag in set(op.tags)
                    for op in circuit_op.circuit.all_operations()
                )
                else []
            ),
            atol=atol,
        )
        for c in resolved_circuits
    ]

    # Step 2, get the new symbolized circuit by symbolizing on indexed symbolized_single_tag.
    new_circuit = tag_transformers.remove_tags(  # remove the temp tags used to track merges
        symbolize.symbolize_single_qubit_gates_by_indexed_tags(
            tag_transformers.index_tags(  # index all 1-qubit-ops merged from ops with symbols
                merged_circuits[0],
                context=transformer_api.TransformerContext(deep=deep),
                target_tags={symbolized_single_tag},
            ),
            symbolize_tag=symbolize.SymbolizeTag(prefix=symbolized_single_tag),
        ),
        remove_if=lambda tag: str(tag).startswith(symbolized_single_tag),
    )

    # Step 3, get N sets of parameterizations as new_sweep.
    if remaining_symbols:
        new_sweep: Sweep = Zip(
            _calc_phxz_sweeps(new_circuit, merged_circuits),  # phxz sweeps
            _sweep_on_symbols(sweep, remaining_symbols),  # remaining sweeps
        )
    else:
        new_sweep = _calc_phxz_sweeps(new_circuit, merged_circuits)

    return align.align_right(new_circuit), new_sweep
