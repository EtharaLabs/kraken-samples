# syntax=docker/dockerfile:1.19@sha256:b6afd42430b15f2d2a4c5a02b919e98a525b785b1aaff16747d2f623364e39b6

# Separate verifier image, never shown to the agent. It carries the pristine base
# tree built in place from source, the reference tree (base plus the upstream source
# change of pull request 10602, the same compiled modules), the pristine covering
# test files, one offline virtual environment from the same hash-pinned lock as the
# agent image (with no statsmodels installed and no .pth), Harbor Reward Kit at the
# release the pinned Harbor commit names, and the measurement harness. The submitted
# working tree arrives at /app/statsmodels as a Harbor artifact.

FROM ghcr.io/astral-sh/uv:0.11.22@sha256:16b63af0e7342dd372da9ca989ea9fa542fc68f4640972d59a8450a5240fe42e AS uv

FROM python:3.13.18-trixie@sha256:51db6babcbd039687e5362a676db5444b5926739abb03b10c8c6a8144872611f AS build
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
COPY --from=uv /uv /usr/local/bin/uv
# The full python:3.13.18-trixie image already carries gcc and libc6-dev; nothing is fetched with apt.
ADD --checksum=sha256:c7f8bc548dedf52e850a0de88f5cc3521b27471f8c780c3e962b34e602d738e6 \
    https://github.com/statsmodels/statsmodels/archive/87f138ebfd53bf3cf91bd389f2592d643f24a6eb.tar.gz /tmp/base.tar.gz
ADD --checksum=sha256:7f93a7710a37cd68697ba1b3c917e2f610669ca5c5f1a7ab28a717e904bd1e82 \
    https://github.com/statsmodels/statsmodels/archive/7e098027b363eb06de9ec174f733a3dcbdd25e93.tar.gz /tmp/expert.tar.gz
ADD --checksum=sha256:2a2e7fd5a87e533b8ecc014836dd78c160a7dd445629ee9795b682d3be5004f9 \
    https://github.com/harbor-framework/harbor/archive/fdba28fc411e47e8765420a1a063b4918fce3def.tar.gz /tmp/harbor.tar.gz
COPY --chown=0:0 build/requirements-sm.txt build/graft.py rewardkit-requirements.txt /tmp/build/
ENV UV_CACHE_DIR=/tmp/uv-cache \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    SETUPTOOLS_SCM_PRETEND_VERSION=0.15.1.dev0
RUN mkdir -p /opt/kraken/base /opt/kraken/pristine-tests /tmp/fix /src/harbor \
 && tar -xzf /tmp/base.tar.gz -C /opt/kraken/base --strip-components=1 \
 && tar -xzf /tmp/expert.tar.gz -C /tmp/fix --strip-components=1 \
 && tar -xzf /tmp/harbor.tar.gz -C /src/harbor --strip-components=1 \
      harbor-fdba28fc411e47e8765420a1a063b4918fce3def/packages/rewardkit \
 && uv venv /opt/venv --python /usr/local/bin/python3.13 \
 && uv pip install --python /opt/venv/bin/python --require-hashes -r /tmp/build/requirements-sm.txt \
 && uv pip install --python /opt/venv/bin/python --no-build-isolation --no-deps /opt/kraken/base \
 && site="$(/opt/venv/bin/python -c 'import sysconfig; print(sysconfig.get_paths()["platlib"])')" \
 && /opt/venv/bin/python /tmp/build/graft.py "${site}/statsmodels" /opt/kraken/base \
 && uv pip uninstall --python /opt/venv/bin/python \
      statsmodels cython meson meson-python ninja setuptools-scm pyproject-metadata \
 && rm -rf /opt/kraken/base/build \
 && cp -a /opt/kraken/base /opt/kraken/expert \
 && cp /tmp/fix/statsmodels/tsa/stattools/_stattools.py /opt/kraken/expert/statsmodels/tsa/stattools/_stattools.py \
 && cp /tmp/fix/statsmodels/tsa/_lagselect.py /opt/kraken/expert/statsmodels/tsa/_lagselect.py \
 && cp /tmp/fix/statsmodels/tsa/tests/test_stattools.py /tmp/fix/statsmodels/tsa/tests/test_lagselect.py \
      /opt/kraken/pristine-tests/ \
 && uv venv /opt/rk --python /usr/local/bin/python3.13 \
 && uv pip install --python /opt/rk/bin/python --require-hashes --no-deps -r /tmp/build/rewardkit-requirements.txt \
 && uv pip install --python /opt/rk/bin/python --no-deps /src/harbor/packages/rewardkit \
 && rm -rf /tmp/uv-cache /tmp/build /tmp/fix /tmp/*.tar.gz /src/harbor /root/.cache \
 && find /opt/kraken /opt/venv /opt/rk -name '__pycache__' -prune -exec rm -rf {} +

FROM python:3.13-slim-trixie@sha256:ae14d4ce8771606477a81446e7ef429edd6762305fc50c84507c1041fa8285d1 AS verifier
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
LABEL org.opencontainers.image.source="https://github.com/statsmodels/statsmodels" \
      org.opencontainers.image.revision="87f138ebfd53bf3cf91bd389f2592d643f24a6eb" \
      org.opencontainers.image.licenses="BSD-3-Clause"
RUN groupadd -g 10001 runner \
 && useradd -u 10001 -g 10001 -M -d /nonexistent -s /usr/sbin/nologin runner \
 && find / -xdev -type f -perm /6000 -exec chmod a-s {} +
COPY --from=build /opt/venv /opt/venv
COPY --from=build /opt/rk /opt/rk
COPY --from=build /opt/kraken /opt/kraken
# The covering-test pass set depends only on the trees and the test runner, so it is
# recorded before the rest of the harness lands and survives harness edits in the cache.
COPY --chown=0:0 harness/runner.py harness/repotests.py harness/tests.json /opt/kraken/harness/
RUN chmod -R a+rX,go-w /opt/kraken \
 && /opt/venv/bin/python -I -B /opt/kraken/harness/repotests.py baseline /opt/kraken/base /opt/kraken/expert \
      /opt/kraken/base-pass.json /opt/kraken/harness/tests.json \
 && chmod 0644 /opt/kraken/base-pass.json \
 && rm -rf /opt/kraken/work /dev/shm/za-scratch
COPY --chown=0:0 harness/ /opt/kraken/harness/
COPY --chown=0:0 judge_guard.py /opt/kraken/
COPY --chown=0:0 test.sh reward.toml judge.toml cheat-checks.json test_output.py diag_correctness.py diag_speedup.py diag_noise.py diag_stage.py /tests/
RUN chmod -R a+rX,go-w /opt/kraken /tests \
 && chmod 0755 /tests/test.sh
ENV PATH=/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1
WORKDIR /opt/kraken
