# syntax=docker/dockerfile:1.19@sha256:b6afd42430b15f2d2a4c5a02b919e98a525b785b1aaff16747d2f623364e39b6

# Separate verifier image. It carries the pristine base source, a pristine base build,
# a reference build (base plus the fast reference implementation in expert/), a warm
# base tree the submission is overlaid on and recompiled in, the compiler toolchain for
# that rebuild (identical to the agent image's), Harbor Reward Kit at the release the
# pinned Harbor commit names, and the measurement harness. The submitted working tree
# arrives at /app/scikit-learn as a Harbor artifact.

FROM --platform=$BUILDPLATFORM ghcr.io/astral-sh/uv:0.11.22@sha256:16b63af0e7342dd372da9ca989ea9fa542fc68f4640972d59a8450a5240fe42e AS uv

# Stage fetch: architecture-independent downloads, each checked by sha256.
FROM --platform=$BUILDPLATFORM python:3.13-slim-trixie@sha256:d98cc29d3266e535dd9da1099688d9cb3ca4753813571e071763d17725460962 AS fetch
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ADD --checksum=sha256:2b61c4571f73f34421c20d09c495cef3446671610e591ec4bc6d3a8698fe5eaa \
    https://github.com/scikit-learn/scikit-learn/archive/9ddf4d35c20f780451aefd1c94c268da6367e4de.tar.gz /tmp/dl/base.tar.gz
ADD --checksum=sha256:2a2e7fd5a87e533b8ecc014836dd78c160a7dd445629ee9795b682d3be5004f9 \
    https://github.com/harbor-framework/harbor/archive/fdba28fc411e47e8765420a1a063b4918fce3def.tar.gz /tmp/dl/harbor.tar.gz
COPY --chown=0:0 expert/ /tmp/expert/
RUN mkdir -p /src/base /src/expert /src/harbor \
 && tar -xzf /tmp/dl/base.tar.gz -C /src/base --strip-components=1 \
 && rm -rf /src/base/.github /src/base/.circleci \
 && find /src/base -name '.git*' ! -name '.gitignore' ! -name '.gitattributes' -prune -exec rm -rf {} + \
 && for rel in sklearn/linear_model/_cd_fast.pyx sklearn/linear_model/_coordinate_descent.py; do \
      install -D -m 0644 "/tmp/expert/$rel" "/src/expert/$rel"; \
    done \
 && tar -xzf /tmp/dl/harbor.tar.gz -C /src/harbor --strip-components=1 \
      harbor-fdba28fc411e47e8765420a1a063b4918fce3def/packages/rewardkit \
 && rm -rf /tmp/dl /tmp/expert

# Stage toolchain: the compiler and Python packages the verifier rebuilds and runs with,
# identical to the agent image's toolchain stage.
FROM python:3.13.17-trixie@sha256:d5a186865324088bd10d1671801b42297a8fe3f8059143fb22b2e2b776ffa6dd AS toolchain
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
COPY --chown=0:0 sk-requirements.txt /tmp/sk-requirements.txt
RUN python3 -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir --require-hashes -r /tmp/sk-requirements.txt \
 && rm -f /tmp/sk-requirements.txt \
 && find /opt/venv -name '__pycache__' -prune -exec rm -rf {} +

# Stage rewardkit: Reward Kit in its own virtual environment.
FROM toolchain AS rewardkit
ARG TARGETOS
ARG TARGETARCH
COPY --from=uv /uv /usr/local/bin/uv
COPY --from=fetch /src/harbor /src/harbor
COPY --chown=0:0 rewardkit-requirements.txt /tmp/rewardkit-requirements.txt
RUN case "${TARGETOS:-linux}/${TARGETARCH:-$(dpkg --print-architecture)}" in \
      linux/amd64) plat=x86_64-unknown-linux-gnu ;; \
      linux/arm64) plat=aarch64-unknown-linux-gnu ;; \
      *) echo "unsupported platform ${TARGETOS}/${TARGETARCH}" >&2; exit 1 ;; \
    esac \
 && UV_CACHE_DIR=/tmp/uv-cache UV_PYTHON_DOWNLOADS=never uv venv /opt/rk --python /usr/local/bin/python3.13 \
 && UV_CACHE_DIR=/tmp/uv-cache uv pip install --python /opt/rk/bin/python --python-platform="${plat}" --require-hashes \
      -r /tmp/rewardkit-requirements.txt \
 && UV_CACHE_DIR=/tmp/uv-cache uv pip install --python /opt/rk/bin/python --python-platform="${plat}" --no-deps \
      /src/harbor/packages/rewardkit \
 && rm -rf /tmp/uv-cache /src/harbor /tmp/rewardkit-requirements.txt \
 && find /opt/rk -name '__pycache__' -prune -exec rm -rf {} +

# Stage builds: the base build, the reference build and the warm tree.
FROM toolchain AS builds
COPY --from=fetch /src/base /src/base
COPY --from=fetch /src/expert /src/expert
COPY --chown=0:0 harness/build.py harness/runner.py /opt/harness/bin/
RUN PYTHONDONTWRITEBYTECODE=1 /opt/venv/bin/python /opt/harness/bin/build.py image /src/base /src/expert \
 && rm -rf /opt/harness/bin /src/base /src/expert /root/.cache \
 && find /opt/harness -name '__pycache__' -prune -exec rm -rf {} +

FROM toolchain AS verifier
LABEL org.opencontainers.image.source="https://github.com/scikit-learn/scikit-learn" \
      org.opencontainers.image.revision="9ddf4d35c20f780451aefd1c94c268da6367e4de" \
      org.opencontainers.image.licenses="BSD-3-Clause"
RUN groupadd -g 10001 runner \
 && useradd -u 10001 -g 10001 -M -d /nonexistent -s /usr/sbin/nologin runner \
 && groupadd -g 10002 builder \
 && useradd -u 10002 -g 10002 -M -d /nonexistent -s /usr/sbin/nologin builder \
 && find / -xdev -type f -perm /6000 -exec chmod a-s {} +
COPY --from=rewardkit /opt/rk /opt/rk
COPY --from=builds /opt/harness /opt/harness
ENV PATH=/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    PYTHONDONTWRITEBYTECODE=1 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1
# The base pass set depends only on the test runner and the base build, so it is
# recorded before the rest of the harness lands and survives harness edits in the cache.
COPY --chown=0:0 harness/runner.py harness/repotests.py harness/config.json /opt/harness/bin/
RUN chmod -R a+rX,go-w /opt/harness \
 && /opt/venv/bin/python /opt/harness/bin/repotests.py baseline /opt/harness/base-site \
      /opt/harness/base-pass.json /opt/harness/bin/config.json \
 && rm -rf /opt/harness/scratch \
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
CMD ["/bin/bash"]
