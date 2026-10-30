#!/usr/bin/env bash
# FORGE-CANARY-BEGIN
# FORGE-CANARY-SLOT-1: 0000000000000000000000000000000000000000000000000000000000000000
# FORGE-CANARY-SLOT-2: 0000000000000000000000000000000000000000000000000000000000000000
# FORGE-CANARY-SLOT-3: 0000000000000000000000000000000000000000000000000000000000000000
# FORGE-CANARY-END
# GENERATED SECTION. DO NOT HAND-EDIT.
# Oracle ladder. Every live line is one self-contained command: solution/apply.py
# applies (+) or reverts (-) staged sub-patches on /app/pennylane with exact context.
# Each prefix of the lines is a real partial fix; the last line reverts the stages and
# applies solution/reference.patch, so the full oracle tree is base plus the upstream fix.
# S1: remove_from_program (queuing.py) uses the backward sweep; fixes the CNOT-style family
python3 "$(dirname "$0")/apply.py" +stages/1-remove-from-program.patch
# S2: create_controlled_op2 (controlled.py) uses it; part of the qp.ctrl family
python3 "$(dirname "$0")/apply.py" +stages/2-controlled-create.patch
# S3: Controlled2._bind_primitive (controlled2.py) uses it; the rest of qp.ctrl, most of the nested family
python3 "$(dirname "$0")/apply.py" +stages/3-controlled-bind.patch
# S4: _make_adjoint_op (adjoint.py) uses it; the qp.adjoint family and the rest of the nested family
python3 "$(dirname "$0")/apply.py" +stages/4-adjoint.patch
# S5: remove_from_program takes many operators and CompositeOp2 removes its operands eight at a time, one backward sweep per chunk; the qp.prod family clears tau but stays slower than the expert (a partial share), because the sweeps still grow with the number of chunks
python3 "$(dirname "$0")/apply.py" +stages/5-composite-chunked.patch
# U: revert the stages and apply the upstream fix
python3 "$(dirname "$0")/apply.py" -stages/5-composite-chunked.patch -stages/4-adjoint.patch -stages/3-controlled-bind.patch -stages/2-controlled-create.patch -stages/1-remove-from-program.patch +reference.patch
