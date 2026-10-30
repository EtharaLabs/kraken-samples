# syntax=docker/dockerfile:1.19@sha256:b6afd42430b15f2d2a4c5a02b919e98a525b785b1aaff16747d2f623364e39b6

# Separate verifier image. It carries the pristine base tree, the expert tree
# (base with the upstream source change), one offline virtual environment from
# the repository's own uv.lock, Harbor Reward Kit at the release the pinned Harbor
# commit names, and the measurement harness. The submitted working tree arrives
# at /app/pennylane as a Harbor artifact.

FROM --platform=$BUILDPLATFORM ghcr.io/astral-sh/uv:0.11.22@sha256:16b63af0e7342dd372da9ca989ea9fa542fc68f4640972d59a8450a5240fe42e AS uv

FROM --platform=$BUILDPLATFORM python:3.13-slim-trixie@sha256:d98cc29d3266e535dd9da1099688d9cb3ca4753813571e071763d17725460962 AS fetch
ARG TARGETOS
ARG TARGETARCH
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
COPY --from=uv /uv /usr/local/bin/uv
ADD --checksum=sha256:c070e2bf1decb6e57adb78bdf366fe1a68d141e1886757901054927ad72013f5 \
    https://github.com/PennyLaneAI/pennylane/archive/d5e813f5ae304acb0e90251351b9b9ea4328a895.tar.gz /tmp/base.tar.gz
ADD --checksum=sha256:fbd999b35e2f6b68986395009185aaf68a41f973054f15ab4c932593d7ab49cf \
    https://github.com/PennyLaneAI/pennylane/archive/8c40ed916ee90c34bbaf143b3c74e33ac2453758.tar.gz /tmp/expert.tar.gz
ADD --checksum=sha256:2a2e7fd5a87e533b8ecc014836dd78c160a7dd445629ee9795b682d3be5004f9 \
    https://github.com/harbor-framework/harbor/archive/fdba28fc411e47e8765420a1a063b4918fce3def.tar.gz /tmp/harbor.tar.gz
RUN mkdir -p /opt/kraken/base /opt/kraken/expert /opt/kraken/expert-tests /tmp/fix /src/harbor \
 && tar -xzf /tmp/base.tar.gz -C /opt/kraken/base --strip-components=1 \
 && tar -xzf /tmp/base.tar.gz -C /opt/kraken/expert --strip-components=1 \
 && tar -xzf /tmp/expert.tar.gz -C /tmp/fix --strip-components=1 \
 && rm -rf /opt/kraken/expert/pennylane \
 && cp -a /tmp/fix/pennylane /opt/kraken/expert/pennylane \
 && cp /tmp/fix/tests/core/operator/test_pop_op_eqns.py /opt/kraken/expert-tests/test_pop_op_eqns.py \
 && tar -xzf /tmp/harbor.tar.gz -C /src/harbor --strip-components=1 \
      harbor-fdba28fc411e47e8765420a1a063b4918fce3def/packages/rewardkit \
 && rm -rf /tmp/base.tar.gz /tmp/expert.tar.gz /tmp/harbor.tar.gz /tmp/fix
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON=/usr/local/bin/python3.13 \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    UV_CACHE_DIR=/tmp/uv-cache
COPY rewardkit-requirements.txt /tmp/rewardkit-requirements.txt
WORKDIR /opt/kraken/base
RUN case "${TARGETOS}/${TARGETARCH}" in \
      linux/amd64) plat=x86_64-unknown-linux-gnu ;; \
      linux/arm64) plat=aarch64-unknown-linux-gnu ;; \
      *) echo "unsupported platform ${TARGETOS}/${TARGETARCH}" >&2; exit 1 ;; \
    esac \
 && uv sync --locked --group dev --python-platform="${plat}" \
 && uv venv /opt/rk --python /usr/local/bin/python3.13 \
 && uv pip install --python /opt/rk/bin/python --python-platform="${plat}" --require-hashes \
      -r /tmp/rewardkit-requirements.txt \
 && uv pip install --python /opt/rk/bin/python --python-platform="${plat}" --no-deps \
      /src/harbor/packages/rewardkit \
 && rm -rf /tmp/uv-cache /src/harbor \
 && find /opt/kraken -name '__pycache__' -prune -exec rm -rf {} + \
 && rm -rf /opt/kraken/base/build /opt/kraken/base/*.egg-info

FROM python:3.13-slim-trixie@sha256:d98cc29d3266e535dd9da1099688d9cb3ca4753813571e071763d17725460962 AS verifier
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
LABEL org.opencontainers.image.source="https://github.com/PennyLaneAI/pennylane" \
      org.opencontainers.image.revision="d5e813f5ae304acb0e90251351b9b9ea4328a895" \
      org.opencontainers.image.licenses="Apache-2.0"
RUN groupadd -g 10000 verifier \
 && useradd -u 10000 -g 10000 -M -d /nonexistent -s /usr/sbin/nologin verifier \
 && groupadd -g 10001 runner \
 && useradd -u 10001 -g 10001 -M -d /nonexistent -s /usr/sbin/nologin runner \
 && find / -xdev -type f -perm /6000 -exec chmod a-s {} +
COPY --from=fetch /opt/venv /opt/venv
COPY --from=fetch /opt/rk /opt/rk
COPY --from=fetch /opt/kraken /opt/kraken
# The base pass set depends only on the test runner, so it is recorded before the
# rest of the harness lands and survives harness edits in the build cache.
COPY harness/runner.py harness/repotests.py harness/tests.json /opt/kraken/harness/
RUN chmod -R a+rX,go-w /opt/kraken \
 && cp /opt/kraken/expert-tests/test_pop_op_eqns.py /opt/kraken/base/tests/core/operator/test_pop_op_eqns.py \
 && /opt/venv/bin/python /opt/kraken/harness/repotests.py baseline /opt/kraken/base \
      /opt/kraken/base-pass.json /opt/kraken/harness/tests.json \
 && rm /opt/kraken/base/tests/core/operator/test_pop_op_eqns.py \
 && chmod 0644 /opt/kraken/base-pass.json \
 && rm -rf /opt/kraken/scratch
COPY harness/ /opt/kraken/harness/
COPY judge_guard.py reward.compiled.toml /opt/kraken/
COPY test.sh reward.toml judge.toml test_output.py diag_correctness.py diag_speedup.py /tests/
RUN chmod -R a+rX,go-w /opt/kraken /tests \
 && chmod 0755 /tests/test.sh
ENV PATH=/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    JAX_PLATFORMS=cpu \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1
WORKDIR /opt/kraken
USER 10000:10000
