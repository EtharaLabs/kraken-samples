# syntax=docker/dockerfile:1.19@sha256:b6afd42430b15f2d2a4c5a02b919e98a525b785b1aaff16747d2f623364e39b6

# Agent sandbox: the numpy source tree at the pinned base commit with its vendored
# submodules (no version-control history, no remotes), built editable in place with
# meson, plus the compiler toolchain needed to rebuild it, and the visible workload.

# Stage 1, fetch: architecture-independent downloads, each checked by sha256.
FROM --platform=$BUILDPLATFORM python:3.13-slim-trixie@sha256:d98cc29d3266e535dd9da1099688d9cb3ca4753813571e071763d17725460962 AS fetch
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ADD --checksum=sha256:82d6a7ab577708aa3f978e44c3e8b7aa739cd2cadd2f10bdaf3f3f7d52f209b8 \
    https://github.com/numpy/numpy/archive/a73316f07a23323e3f86a861f967e2457277e903.tar.gz /tmp/dl/numpy.tar.gz
# numpy's six vendored submodules at the commits the base tree pins, fetched in one step and
# checked against their sha256. The script runs inline, one quoted line per argument, not as a
# heredoc: Kaniko drops heredoc bodies.
RUN mkdir -p /tmp/dl && printf '%s\n' \
    'import hashlib, urllib.request' \
    'PINS = [' \
    '    ("meson.tar.gz", "https://github.com/numpy/meson/archive/983fca5b39b62060c733a58fd8ecd276591bdf12.tar.gz",' \
    '     "8b9ac79e1f9a71f78bf1158170a693313049d37e9c7d49d785c5adfe9d2b3539"),' \
    '    ("pythoncapi-compat.tar.gz", "https://github.com/python/pythoncapi-compat/archive/8636bccf29adfa23463f810b3c2830f7cff1e933.tar.gz",' \
    '     "228ead329df7487a1e7bf97c45a3ed239a1f427ce181407af5657bf95a227357"),' \
    '    ("highway.tar.gz", "https://github.com/google/highway/archive/ee36c837129310be19c17c9108c6dc3f6ae06942.tar.gz",' \
    '     "354c62cce7f43305f7a254344e3cb5a79fa6395298d9e003b07e410c2c179676"),' \
    '    ("x86-simd-sort.tar.gz", "https://github.com/intel/x86-simd-sort/archive/fa944efbea1a33426b3f8a9a21e23794ab8aa300.tar.gz",' \
    '     "f932aa2e2c19aa0374e5bcc1714308c1498d622b9139b841cdd219d0444bb3a0"),' \
    '    ("svml.tar.gz", "https://github.com/numpy/SVML/archive/bd9d46e0c627ab16f3d2641f7cdb1bc15d303ba4.tar.gz",' \
    '     "7c4484ce01858eaec3617e16f079bfba19d4c825800ad94908b4fc1b1e45369e"),' \
    '    ("pocketfft.tar.gz", "https://github.com/mreineck/pocketfft/archive/33ae5dc94c9cdc7f1c78346504a85de87cadaa12.tar.gz",' \
    '     "c338c55e8d5c505e6feb3cac868631b5a68812a878d9852a242e39130ecec647"),' \
    ']' \
    'for name, url, sha256 in PINS:' \
    '    with urllib.request.urlopen(url, timeout=600) as response:' \
    '        data = response.read()' \
    '    digest = hashlib.sha256(data).hexdigest()' \
    '    if digest != sha256:' \
    '        raise SystemExit(f"sha256 mismatch for {url}: got {digest}, pinned {sha256}")' \
    '    with open("/tmp/dl/" + name, "wb") as out:' \
    '        out.write(data)' \
  | python3 -
RUN set -e; src=/src/numpy; mkdir -p "$src" \
 && tar -xzf /tmp/dl/numpy.tar.gz -C "$src" --strip-components=1 \
 && for pair in meson:vendored-meson/meson pythoncapi-compat:numpy/_core/src/common/pythoncapi-compat \
                highway:numpy/_core/src/highway x86-simd-sort:numpy/_core/src/npysort/x86-simd-sort \
                svml:numpy/_core/src/umath/svml pocketfft:numpy/fft/pocketfft; do \
      name="${pair%%:*}"; dest="$src/${pair#*:}"; rm -rf "$dest"; mkdir -p "$dest"; \
      tar -xzf "/tmp/dl/${name}.tar.gz" -C "$dest" --strip-components=1; \
    done \
 && find "$src" -name '.git*' ! -name '.gitignore' ! -name '.gitattributes' -prune -exec rm -rf {} + \
 && rm -rf "$src/.github" "$src/.circleci" /tmp/dl

# Stage 2, toolchain: the compiler and Python build tools the agent itself runs to
# rebuild numpy: gcc, g++ and pkg-config from the full python:3.13.17-trixie image (nothing
# is fetched with apt), Python tools from a hash-locked requirements file.
FROM python:3.13.17-trixie@sha256:d5a186865324088bd10d1671801b42297a8fe3f8059143fb22b2e2b776ffa6dd AS toolchain
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
COPY --chown=0:0 requirements-build.txt /tmp/requirements-build.txt
RUN python3 -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir --require-hashes -r /tmp/requirements-build.txt \
 && rm -f /tmp/requirements-build.txt \
 && find /opt/venv -name '__pycache__' -prune -exec rm -rf {} +

# Stage 3, runtime: the agent sandbox.
FROM toolchain AS runtime
LABEL org.opencontainers.image.source="https://github.com/numpy/numpy" \
      org.opencontainers.image.revision="a73316f07a23323e3f86a861f967e2457277e903" \
      org.opencontainers.image.licenses="BSD-3-Clause"
RUN groupadd -g 1000 agent \
 && useradd -u 1000 -g 1000 -m -d /home/agent -s /bin/bash agent \
 && find / -xdev -type f -perm /6000 -exec chmod a-s {} + \
 && mkdir -p /logs && chmod 0755 /logs
COPY --from=fetch --chown=1000:1000 /src/numpy /app/numpy
ENV PATH=/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    VIRTUAL_ENV=/opt/venv \
    PIP_NO_INDEX=1 \
    PIP_NO_CACHE_DIR=1 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1
WORKDIR /app/numpy
# Four compile jobs: one job per visible CPU runs a many-core builder out of memory.
RUN pip install --no-build-isolation --no-deps -e . -Cbuild-dir=build -Ccompile-args=-j4 \
 && chown -R 1000:1000 /app/numpy \
 && find /app/numpy /opt/venv -name '__pycache__' -prune -exec rm -rf {} + \
 && rm -rf /root/.cache
COPY --chown=0:0 workload/ /app/workload/
RUN chmod -R a+rX,go-w /app/workload
WORKDIR /app
# Final image user is root for the Smoldata Oracle sandbox; the agent still runs as
# 1000:1000 through [agent].user in task.toml.
USER root
CMD ["/bin/bash"]
