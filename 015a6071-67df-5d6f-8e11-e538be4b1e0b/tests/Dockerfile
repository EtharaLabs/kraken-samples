# syntax=docker/dockerfile:1.19@sha256:b6afd42430b15f2d2a4c5a02b919e98a525b785b1aaff16747d2f623364e39b6

# Separate verifier image. It carries the pristine base tree, the expert tree (the base tree
# with the fast reference implementation in expert/ laid over it), the versions of the
# covering test files from the upstream fix commit, one offline virtual environment from the
# same hash-locked requirements as the agent image, Harbor Reward Kit at the release the
# pinned Harbor commit names, and the measurement harness. The submitted working tree
# arrives at /app/cirq as a Harbor artifact.

FROM --platform=$BUILDPLATFORM ghcr.io/astral-sh/uv:0.11.22@sha256:16b63af0e7342dd372da9ca989ea9fa542fc68f4640972d59a8450a5240fe42e AS uv

FROM --platform=$BUILDPLATFORM python:3.13-slim-trixie@sha256:d98cc29d3266e535dd9da1099688d9cb3ca4753813571e071763d17725460962 AS fetch
ARG TARGETOS
ARG TARGETARCH
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
COPY --from=uv /uv /usr/local/bin/uv
ADD --checksum=sha256:f89dc22e1825280199bbbe66b1b06ea66b4e5eb19a56c3fd933ba11bb8266bda \
    https://github.com/quantumlib/Cirq/archive/0fe0535e1fc206f0bfeabb3437e9753676d187a1.tar.gz /tmp/base.tar.gz
ADD --checksum=sha256:f6d2c3b0319268d1e318203fcd7d409e2207eaf42d2b5a59c9a4a244aa10294f \
    https://github.com/quantumlib/Cirq/archive/5539290c459696f14043a973dfab11df48a69867.tar.gz /tmp/fix.tar.gz
ADD --checksum=sha256:2a2e7fd5a87e533b8ecc014836dd78c160a7dd445629ee9795b682d3be5004f9 \
    https://github.com/harbor-framework/harbor/archive/fdba28fc411e47e8765420a1a063b4918fce3def.tar.gz /tmp/harbor.tar.gz
COPY --chown=0:0 expert/ /tmp/expert/
RUN mkdir -p /opt/harness/base /opt/harness/expert /opt/harness/overlay /tmp/fix /src/harbor \
 && tar -xzf /tmp/base.tar.gz -C /opt/harness/base --strip-components=1 \
 && tar -xzf /tmp/base.tar.gz -C /opt/harness/expert --strip-components=1 \
 && tar -xzf /tmp/fix.tar.gz -C /tmp/fix --strip-components=1 \
 && for f in cirq-core/cirq/circuits/circuit_operation.py \
             cirq-core/cirq/ops/single_qubit_unitary.py \
             cirq-core/cirq/transformers/analytical_decompositions/single_qubit_decompositions.py \
             cirq-core/cirq/transformers/merge_k_qubit_gates.py \
             cirq-core/cirq/transformers/merge_single_qubit_gates.py \
             cirq-core/cirq/transformers/transformer_primitives.py; do \
      install -m 0644 "/tmp/expert/$f" "/opt/harness/expert/$f"; \
    done \
 && for f in cirq-core/cirq/circuits/circuit_operation_test.py \
             cirq-core/cirq/transformers/merge_single_qubit_gates_test.py \
             cirq-core/cirq/transformers/merge_k_qubit_gates_test.py; do \
      mkdir -p "/opt/harness/overlay/$(dirname "$f")" && cp "/tmp/fix/$f" "/opt/harness/overlay/$f"; \
    done \
 && tar -xzf /tmp/harbor.tar.gz -C /src/harbor --strip-components=1 \
      harbor-fdba28fc411e47e8765420a1a063b4918fce3def/packages/rewardkit \
 && rm -rf /tmp/base.tar.gz /tmp/fix.tar.gz /tmp/harbor.tar.gz /tmp/fix /tmp/expert
COPY --chown=0:0 cirq-requirements.txt rewardkit-requirements.txt /tmp/
ENV UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    UV_CACHE_DIR=/tmp/uv-cache
RUN case "${TARGETOS:-linux}/${TARGETARCH:-$(dpkg --print-architecture)}" in \
      linux/amd64) plat=x86_64-unknown-linux-gnu ;; \
      linux/arm64) plat=aarch64-unknown-linux-gnu ;; \
      *) echo "unsupported platform ${TARGETOS}/${TARGETARCH}" >&2; exit 1 ;; \
    esac \
 && uv venv /opt/venv --python /usr/local/bin/python3.13 \
 && uv pip install --python /opt/venv/bin/python --python-platform "${plat}" --require-hashes \
      -r /tmp/cirq-requirements.txt \
 && uv venv /opt/rk --python /usr/local/bin/python3.13 \
 && uv pip install --python /opt/rk/bin/python --python-platform "${plat}" --require-hashes \
      -r /tmp/rewardkit-requirements.txt \
 && uv pip install --python /opt/rk/bin/python --python-platform "${plat}" --no-deps \
      /src/harbor/packages/rewardkit \
 && rm -rf /tmp/uv-cache /src/harbor /tmp/*.txt \
 && find /opt/harness -name '__pycache__' -prune -exec rm -rf {} +

FROM python:3.13-slim-trixie@sha256:d98cc29d3266e535dd9da1099688d9cb3ca4753813571e071763d17725460962 AS verifier
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
LABEL org.opencontainers.image.source="https://github.com/quantumlib/Cirq" \
      org.opencontainers.image.revision="0fe0535e1fc206f0bfeabb3437e9753676d187a1" \
      org.opencontainers.image.licenses="Apache-2.0"
RUN groupadd -g 10001 runner \
 && useradd -u 10001 -g 10001 -M -d /nonexistent -s /usr/sbin/nologin runner \
 && find / -xdev -type f -perm /6000 -exec chmod a-s {} +
COPY --from=fetch /opt/venv /opt/venv
COPY --from=fetch /opt/rk /opt/rk
COPY --from=fetch /opt/harness /opt/harness
ENV PATH=/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    MPLBACKEND=agg \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1
# The base pass set depends only on the test runner and the trees, so it is recorded
# before the rest of the harness lands and survives harness edits in the build cache.
COPY --chown=0:0 harness/runner.py harness/repotests.py harness/config.json /opt/harness/bin/
RUN chmod -R a+rX,go-w /opt/harness \
 && rm -rf /opt/harness/work && cp -a /opt/harness/base /opt/harness/work \
 && for f in $(cd /opt/harness/overlay && find . -type f); do cp "/opt/harness/overlay/$f" "/opt/harness/work/$f"; done \
 && chmod -R a+rX,go-w /opt/harness/work \
 && /opt/venv/bin/python /opt/harness/bin/repotests.py baseline /opt/harness/work \
      /opt/harness/base-pass.json /opt/harness/bin/config.json \
 && rm -rf /opt/harness/work /opt/harness/scratch \
 && chmod 0644 /opt/harness/base-pass.json
COPY --chown=0:0 harness/ /opt/harness/bin/
COPY --chown=0:0 score.py judge_guard.py /opt/harness/
COPY --chown=0:0 test.sh judge.toml /tests/
RUN chmod -R a+rX,go-w /opt/harness /tests \
 && chmod 0755 /tests/test.sh \
 && /opt/venv/bin/python -c "import hashlib, json, pathlib; \
files = sorted(str(p) for p in pathlib.Path('/opt/harness/bin').glob('*') if p.is_file()) \
  + ['/opt/harness/score.py', '/opt/harness/judge_guard.py', '/opt/harness/base-pass.json', \
     '/tests/test.sh', '/tests/judge.toml']; \
pathlib.Path('/opt/harness/integrity.json').write_text(json.dumps( \
  {f: hashlib.sha256(pathlib.Path(f).read_bytes()).hexdigest() for f in files}, indent=1))" \
 && chmod 0644 /opt/harness/integrity.json
WORKDIR /opt/harness
