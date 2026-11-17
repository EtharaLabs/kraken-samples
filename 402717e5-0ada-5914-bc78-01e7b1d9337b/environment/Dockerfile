# syntax=docker/dockerfile:1.19@sha256:b6afd42430b15f2d2a4c5a02b919e98a525b785b1aaff16747d2f623364e39b6

# Agent sandbox: the statsmodels source tree at the pinned base commit (no version
# control history), built in place from source with hash-pinned build and runtime
# dependencies, and the visible workload. The tree is importable directly: a saved
# edit to a .py file is picked up by the next interpreter.

FROM ghcr.io/astral-sh/uv:0.11.22@sha256:16b63af0e7342dd372da9ca989ea9fa542fc68f4640972d59a8450a5240fe42e AS uv

# The extension modules are compiled for the target platform, so this stage runs on
# the target platform (natively or emulated), not on the build platform.
FROM python:3.13.18-trixie@sha256:51db6babcbd039687e5362a676db5444b5926739abb03b10c8c6a8144872611f AS build
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
COPY --from=uv /uv /usr/local/bin/uv
# The full python:3.13.18-trixie image already carries gcc and libc6-dev; nothing is fetched with apt.
ADD --checksum=sha256:c7f8bc548dedf52e850a0de88f5cc3521b27471f8c780c3e962b34e602d738e6 \
    https://github.com/statsmodels/statsmodels/archive/87f138ebfd53bf3cf91bd389f2592d643f24a6eb.tar.gz /tmp/statsmodels.tar.gz
COPY --chown=0:0 build/requirements-sm.txt build/graft.py /tmp/build/
ENV UV_CACHE_DIR=/tmp/uv-cache \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    SETUPTOOLS_SCM_PRETEND_VERSION=0.15.1.dev0
RUN mkdir -p /app/statsmodels \
 && tar -xzf /tmp/statsmodels.tar.gz -C /app/statsmodels --strip-components=1 \
 && rm /tmp/statsmodels.tar.gz \
 && uv venv /opt/venv --python /usr/local/bin/python3.13 \
 && uv pip install --python /opt/venv/bin/python --require-hashes -r /tmp/build/requirements-sm.txt \
 && uv pip install --python /opt/venv/bin/python --no-build-isolation --no-deps /app/statsmodels \
 && site="$(/opt/venv/bin/python -c 'import sysconfig; print(sysconfig.get_paths()["platlib"])')" \
 && /opt/venv/bin/python /tmp/build/graft.py "${site}/statsmodels" /app/statsmodels \
 && uv pip uninstall --python /opt/venv/bin/python \
      statsmodels cython meson meson-python ninja setuptools-scm pyproject-metadata \
 && printf '/app/statsmodels\n' > "${site}/statsmodels-source-tree.pth" \
 && rm -rf /tmp/uv-cache /tmp/build /root/.cache /app/statsmodels/build \
 && find /app/statsmodels /opt/venv -name '__pycache__' -prune -exec rm -rf {} + \
 && find / -xdev \( -name '*.whl' -o -name 'statsmodels-*.tar.gz' \) -print -delete

FROM python:3.13-slim-trixie@sha256:ae14d4ce8771606477a81446e7ef429edd6762305fc50c84507c1041fa8285d1 AS runtime
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
LABEL org.opencontainers.image.source="https://github.com/statsmodels/statsmodels" \
      org.opencontainers.image.revision="87f138ebfd53bf3cf91bd389f2592d643f24a6eb" \
      org.opencontainers.image.licenses="BSD-3-Clause"
RUN groupadd -g 1000 agent \
 && useradd -u 1000 -g 1000 -m -d /home/agent -s /bin/bash agent \
 && find / -xdev -type f -perm /6000 -exec chmod a-s {} + \
 && rm -rf /root/.cache \
 && mkdir -p /logs \
 && chmod 0755 /logs
COPY --from=build /opt/venv /opt/venv
COPY --from=build --chown=1000:1000 /app/statsmodels /app/statsmodels
COPY --chown=0:0 workload/ /app/workload/
RUN chmod -R a+rX,go-w /app/workload \
 && for n in python python3; do \
      rm -f /usr/local/bin/$n \
      && printf '#!/bin/sh\nexec /opt/venv/bin/python "$@"\n' > /usr/local/bin/$n \
      && chmod 0755 /usr/local/bin/$n; \
    done
ENV VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /app/statsmodels
# The agent runs as 1000:1000 through [agent].user in task.toml; the image itself ends as root,
# as Smoldata's validation sandbox expects.
USER root
