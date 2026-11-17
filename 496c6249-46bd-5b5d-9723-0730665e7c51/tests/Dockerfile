# syntax=docker/dockerfile:1.19@sha256:b6afd42430b15f2d2a4c5a02b919e98a525b785b1aaff16747d2f623364e39b6

# Separate verifier image. It carries the pristine base source, a pristine base build,
# a reference build (base plus the upstream library change and the authored C hash path), a warm base build tree
# the submission is overlaid on and recompiled in, the compiler toolchain for that
# rebuild, Harbor Reward Kit at the release the pinned Harbor commit names, and the
# measurement harness. The submitted working tree arrives at /app/numpy as a Harbor
# artifact.

FROM --platform=$BUILDPLATFORM ghcr.io/astral-sh/uv:0.11.22@sha256:16b63af0e7342dd372da9ca989ea9fa542fc68f4640972d59a8450a5240fe42e AS uv

# Stage fetch: architecture-independent downloads, each checked by sha256.
FROM --platform=$BUILDPLATFORM python:3.13-slim-trixie@sha256:d98cc29d3266e535dd9da1099688d9cb3ca4753813571e071763d17725460962 AS fetch
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ADD --checksum=sha256:82d6a7ab577708aa3f978e44c3e8b7aa739cd2cadd2f10bdaf3f3f7d52f209b8 \
    https://github.com/numpy/numpy/archive/a73316f07a23323e3f86a861f967e2457277e903.tar.gz /tmp/dl/numpy.tar.gz
ADD --checksum=sha256:06446926e3efd54a4aa3778eef000a3f52f6117d37ffc30d37b5e5d8f931c800 \
    https://github.com/numpy/numpy/archive/7643e77e8481c80472efb1c9d29de9898d765187.tar.gz /tmp/dl/expert.tar.gz
ADD --checksum=sha256:2a2e7fd5a87e533b8ecc014836dd78c160a7dd445629ee9795b682d3be5004f9 \
    https://github.com/harbor-framework/harbor/archive/fdba28fc411e47e8765420a1a063b4918fce3def.tar.gz /tmp/dl/harbor.tar.gz
COPY --chown=0:0 expert_patch.py expert-c2.patch /tmp/
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
RUN set -e; src=/src/base; mkdir -p "$src" /src/expert /src/harbor /tmp/fix \
 && tar -xzf /tmp/dl/numpy.tar.gz -C "$src" --strip-components=1 \
 && for pair in meson:vendored-meson/meson pythoncapi-compat:numpy/_core/src/common/pythoncapi-compat \
                highway:numpy/_core/src/highway x86-simd-sort:numpy/_core/src/npysort/x86-simd-sort \
                svml:numpy/_core/src/umath/svml pocketfft:numpy/fft/pocketfft; do \
      name="${pair%%:*}"; dest="$src/${pair#*:}"; rm -rf "$dest"; mkdir -p "$dest"; \
      tar -xzf "/tmp/dl/${name}.tar.gz" -C "$dest" --strip-components=1; \
    done \
 && find "$src" -name '.git*' ! -name '.gitignore' ! -name '.gitattributes' -prune -exec rm -rf {} + \
 && rm -rf "$src/.github" "$src/.circleci" \
 && tar -xzf /tmp/dl/expert.tar.gz -C /tmp/fix --strip-components=1 \
 && for rel in numpy/_core/src/multiarray/stringdtype/dtype.c numpy/dtypes.pyi \
               numpy/lib/_arraysetops_impl.py numpy/testing/_private/utils.py; do \
      mkdir -p "/src/expert/$(dirname "$rel")"; cp "/tmp/fix/$rel" "/src/expert/$rel"; \
    done \
 && python3 /tmp/expert_patch.py /src/expert /tmp/expert-c2.patch \
 && tar -xzf /tmp/dl/harbor.tar.gz -C /src/harbor --strip-components=1 \
      harbor-fdba28fc411e47e8765420a1a063b4918fce3def/packages/rewardkit \
 && rm -rf /tmp/dl /tmp/fix /tmp/expert_patch.py /tmp/expert-c2.patch

# Stage toolchain: the compiler and Python build tools the verifier rebuilds with,
# identical to the agent image's toolchain stage.
FROM python:3.13.17-trixie@sha256:d5a186865324088bd10d1671801b42297a8fe3f8059143fb22b2e2b776ffa6dd AS toolchain
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
COPY --chown=0:0 requirements-build.txt /tmp/requirements-build.txt
RUN python3 -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir --require-hashes -r /tmp/requirements-build.txt \
 && rm -f /tmp/requirements-build.txt \
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
 && UV_CACHE_DIR=/tmp/uv-cache uv venv /opt/rk --python /usr/local/bin/python3.13 \
 && UV_CACHE_DIR=/tmp/uv-cache uv pip install --python /opt/rk/bin/python --python-platform="${plat}" --require-hashes \
      -r /tmp/rewardkit-requirements.txt \
 && UV_CACHE_DIR=/tmp/uv-cache uv pip install --python /opt/rk/bin/python --python-platform="${plat}" --no-deps \
      /src/harbor/packages/rewardkit \
 && rm -rf /tmp/uv-cache /src/harbor /tmp/rewardkit-requirements.txt \
 && find /opt/rk -name '__pycache__' -prune -exec rm -rf {} +

# Stage builds: the base build, the reference build and the warm tree (native, see TRUTH.md).
# pip compiles bytecode into every site it installs, here and at verify time, and the sites
# keep it: the first timed call imports modules lazily, so every build must start alike.
FROM toolchain AS builds
COPY --from=fetch /src/base /src/base
COPY --from=fetch /src/expert /src/expert
COPY --chown=0:0 harness/build.py harness/runner.py /opt/kraken/harness/
RUN PYTHONDONTWRITEBYTECODE=1 /opt/venv/bin/python /opt/kraken/harness/build.py image /src/base /src/expert \
 && rm -rf /opt/kraken/harness /src/base /src/expert /root/.cache

FROM toolchain AS verifier
LABEL org.opencontainers.image.source="https://github.com/numpy/numpy" \
      org.opencontainers.image.revision="a73316f07a23323e3f86a861f967e2457277e903" \
      org.opencontainers.image.licenses="BSD-3-Clause"
RUN groupadd -g 10001 runner \
 && useradd -u 10001 -g 10001 -M -d /nonexistent -s /usr/sbin/nologin runner \
 && groupadd -g 10002 builder \
 && useradd -u 10002 -g 10002 -M -d /nonexistent -s /usr/sbin/nologin builder \
 && find / -xdev -type f -perm /6000 -exec chmod a-s {} +
COPY --from=rewardkit /opt/rk /opt/rk
COPY --from=builds /opt/kraken /opt/kraken
# The base pass set depends only on the test runner, so it is recorded before the rest
# of the harness lands and survives harness edits in the build cache.
COPY --chown=0:0 harness/runner.py harness/repotests.py harness/tests.json /opt/kraken/harness/
RUN chmod -R a+rX,go-w /opt/kraken \
 && PYTHONDONTWRITEBYTECODE=1 /opt/venv/bin/python /opt/kraken/harness/repotests.py baseline /opt/kraken/harness/tests.json \
 && chmod 0644 /opt/kraken/base-pass.json \
 && rm -rf /opt/kraken/scratch
COPY --chown=0:0 harness/ /opt/kraken/harness/
# The judge guard, the compiled-only reward table and the compiled-only diagnostic script live
# outside /tests, so Reward Kit never imports the guard nor discovers the compiled-only table
# as a reward of its own, and /tests carries only the graded path.
COPY --chown=0:0 judge_guard.py reward.compiled.toml compiled_only.sh /opt/kraken/
COPY --chown=0:0 test.sh reward.toml judge.toml test_output.py diag_correctness.py diag_speedup.py cheat-checks.json /tests/
RUN chmod -R a+rX,go-w /opt/kraken /tests \
 && chmod 0755 /tests/test.sh /opt/kraken/compiled_only.sh
ENV PATH=/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    PYTHONDONTWRITEBYTECODE=1 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1
WORKDIR /opt/kraken
CMD ["/bin/bash"]
