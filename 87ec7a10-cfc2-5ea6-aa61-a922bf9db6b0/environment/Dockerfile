# syntax=docker/dockerfile:1.19@sha256:b6afd42430b15f2d2a4c5a02b919e98a525b785b1aaff16747d2f623364e39b6

# Agent sandbox: the PennyLane source tree at the pinned base commit (no version
# control history), an offline virtual environment from a hash-locked requirements
# file (the repository's own uv.lock, main and dev dependencies), PennyLane itself
# installed editable from the tree, and the visible workload.

FROM --platform=$BUILDPLATFORM ghcr.io/astral-sh/uv:0.11.22@sha256:16b63af0e7342dd372da9ca989ea9fa542fc68f4640972d59a8450a5240fe42e AS uv

FROM --platform=$BUILDPLATFORM python:3.13-slim-trixie@sha256:d98cc29d3266e535dd9da1099688d9cb3ca4753813571e071763d17725460962 AS build
ARG TARGETOS
ARG TARGETARCH
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
COPY --from=uv /uv /usr/local/bin/uv
ADD --checksum=sha256:c070e2bf1decb6e57adb78bdf366fe1a68d141e1886757901054927ad72013f5 \
    https://github.com/PennyLaneAI/pennylane/archive/d5e813f5ae304acb0e90251351b9b9ea4328a895.tar.gz /tmp/pennylane.tar.gz
COPY --chown=0:0 pennylane-requirements.txt /tmp/pennylane-requirements.txt
RUN mkdir -p /app/pennylane \
 && tar -xzf /tmp/pennylane.tar.gz -C /app/pennylane --strip-components=1 \
 && rm /tmp/pennylane.tar.gz
ENV UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    UV_CACHE_DIR=/tmp/uv-cache
RUN case "${TARGETOS:-linux}/${TARGETARCH:-$(dpkg --print-architecture)}" in \
      linux/amd64) plat=x86_64-unknown-linux-gnu ;; \
      linux/arm64) plat=aarch64-unknown-linux-gnu ;; \
      *) echo "unsupported platform ${TARGETOS}/${TARGETARCH}" >&2; exit 1 ;; \
    esac \
 && uv venv /opt/venv --python /usr/local/bin/python3.13 \
 && uv pip install --python /opt/venv/bin/python --python-platform "${plat}" --require-hashes --no-deps \
      -r /tmp/pennylane-requirements.txt \
 && uv pip install --python /opt/venv/bin/python --python-platform "${plat}" --no-deps -e /app/pennylane \
 && rm -rf /tmp/uv-cache /tmp/pennylane-requirements.txt \
 && find /app/pennylane -name '__pycache__' -prune -exec rm -rf {} + \
 && rm -rf /app/pennylane/build /app/pennylane/*.egg-info

FROM python:3.13-slim-trixie@sha256:d98cc29d3266e535dd9da1099688d9cb3ca4753813571e071763d17725460962 AS runtime
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
LABEL org.opencontainers.image.source="https://github.com/PennyLaneAI/pennylane" \
      org.opencontainers.image.revision="d5e813f5ae304acb0e90251351b9b9ea4328a895" \
      org.opencontainers.image.licenses="Apache-2.0"
RUN groupadd -g 1000 agent \
 && useradd -u 1000 -g 1000 -m -d /home/agent -s /bin/bash agent \
 && find / -xdev -type f -perm /6000 -exec chmod a-s {} + \
 && mkdir -p /logs \
 && chmod 0755 /logs
COPY --from=build /opt/venv /opt/venv
COPY --from=build --chown=1000:1000 /app/pennylane /app/pennylane
COPY --chown=0:0 workload/ /app/workload/
RUN chmod -R a+rX,go-w /app/workload \
 && for n in python python3; do \
      rm -f /usr/local/bin/$n \
      && printf '#!/bin/sh\nexec /opt/venv/bin/python "$@"\n' > /usr/local/bin/$n \
      && chmod 0755 /usr/local/bin/$n; \
    done
ENV VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    JAX_PLATFORMS=cpu \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    XLA_FLAGS=--xla_cpu_multi_thread_eigen=false
WORKDIR /app/pennylane
# Final image user is root for the Smoldata Oracle sandbox; the agent still runs as
# 1000:1000 through [agent].user in task.toml.
USER root
