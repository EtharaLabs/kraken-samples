# syntax=docker/dockerfile:1.19@sha256:b6afd42430b15f2d2a4c5a02b919e98a525b785b1aaff16747d2f623364e39b6

# Agent sandbox: the scikit-learn source tree at the pinned base commit (no version
# control history), built editable in place with meson-python so that a saved edit to a
# .py or .pyx file is rebuilt on the next import, the compiler toolchain that rebuild
# needs, an offline virtual environment from a hash-locked requirements file, and the
# visible workload.

# Stage fetch: architecture-independent download, checked by sha256.
FROM --platform=$BUILDPLATFORM python:3.13-slim-trixie@sha256:d98cc29d3266e535dd9da1099688d9cb3ca4753813571e071763d17725460962 AS fetch
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ADD --checksum=sha256:2b61c4571f73f34421c20d09c495cef3446671610e591ec4bc6d3a8698fe5eaa \
    https://github.com/scikit-learn/scikit-learn/archive/9ddf4d35c20f780451aefd1c94c268da6367e4de.tar.gz /tmp/sk.tar.gz
RUN mkdir -p /src/scikit-learn \
 && tar -xzf /tmp/sk.tar.gz -C /src/scikit-learn --strip-components=1 \
 && rm -rf /tmp/sk.tar.gz /src/scikit-learn/.github /src/scikit-learn/.circleci \
 && find /src/scikit-learn -name '.git*' ! -name '.gitignore' ! -name '.gitattributes' -prune -exec rm -rf {} +

# Stage toolchain: the C/C++ compilers the full python:3.13.17-trixie image carries (nothing
# is fetched with apt) and
# the Python build and runtime packages from a hash-locked requirements file.
FROM python:3.13.17-trixie@sha256:d5a186865324088bd10d1671801b42297a8fe3f8059143fb22b2e2b776ffa6dd AS toolchain
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
COPY --chown=0:0 sk-requirements.txt /tmp/sk-requirements.txt
RUN python3 -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir --require-hashes -r /tmp/sk-requirements.txt \
 && rm -f /tmp/sk-requirements.txt \
 && find /opt/venv -name '__pycache__' -prune -exec rm -rf {} +

# Stage runtime: the agent sandbox.
FROM toolchain AS runtime
LABEL org.opencontainers.image.source="https://github.com/scikit-learn/scikit-learn" \
      org.opencontainers.image.revision="9ddf4d35c20f780451aefd1c94c268da6367e4de" \
      org.opencontainers.image.licenses="BSD-3-Clause"
RUN groupadd -g 1000 agent \
 && useradd -u 1000 -g 1000 -m -d /home/agent -s /bin/bash agent \
 && find / -xdev -type f -perm /6000 -exec chmod a-s {} + \
 && mkdir -p /logs && chmod 0755 /logs
COPY --from=fetch --chown=1000:1000 /src/scikit-learn /app/scikit-learn
ENV PATH=/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    VIRTUAL_ENV=/opt/venv \
    PIP_NO_INDEX=1 \
    PIP_NO_CACHE_DIR=1 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1
WORKDIR /app/scikit-learn
RUN pip install --no-build-isolation --no-deps -e . -Cbuild-dir=build \
 && chown -R 1000:1000 /app/scikit-learn \
 && find /app/scikit-learn /opt/venv -name '__pycache__' -prune -exec rm -rf {} + \
 && rm -rf /root/.cache
COPY --chown=0:0 workload/ /app/workload/
RUN chmod -R a+rX,go-w /app/workload
WORKDIR /app/scikit-learn
# Final image user is root for the Smoldata Oracle sandbox; the agent still runs as
# 1000:1000 through [agent].user in task.toml.
USER root
CMD ["/bin/bash"]
