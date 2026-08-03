# syntax=docker/dockerfile:1.6
FROM ubuntu:22.04

ARG DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH=/opt/miniconda3/bin:$PATH \
    LC_ALL=C.UTF-8 \
    LANG=C.UTF-8

RUN apt-get update && apt-get install -y --no-install-recommends \
        wget git curl jq ca-certificates \
        build-essential gcc gfortran pkg-config \
        python3 python3-pip python-is-python3 python3-dev python3-setuptools \
        libffi-dev libtiff-dev libssl-dev zlib1g-dev \
        libopenblas-dev libblas-dev liblapack-dev \
        locales locales-all tzdata \
    && rm -rf /var/lib/apt/lists/*

RUN CONDA_ARCH=$(uname -m) \
 && wget -q "https://repo.anaconda.com/miniconda/Miniconda3-py311_24.7.1-0-Linux-${CONDA_ARCH}.sh" -O /tmp/miniconda.sh \
 && bash /tmp/miniconda.sh -b -p /opt/miniconda3 \
 && rm /tmp/miniconda.sh \
 && /opt/miniconda3/bin/conda config --append channels conda-forge \
 && /opt/miniconda3/bin/conda clean --all --yes

RUN git config --global user.email harbor@local \
 && git config --global user.name harbor \
 && git config --global advice.detachedHead false

# --- Tier 2: clone repo at base_commit ---
COPY setup_repo.sh /root/setup_repo.sh
RUN chmod +x /root/setup_repo.sh && bash /root/setup_repo.sh

# --- Tier 3: create conda testbed env, install repo, tag harbor-base ---
COPY setup_env.sh /root/setup_env.sh
RUN chmod +x /root/setup_env.sh && bash /root/setup_env.sh

RUN echo 'source /opt/miniconda3/etc/profile.d/conda.sh && conda activate testbed' > /root/.bashrc
ENV BASH_ENV=/root/.bashrc
SHELL ["/bin/bash", "-lc"]

# test_patch is applied at EVAL time by tests/test.sh, never baked into git.
RUN mkdir -p /opt/harbor
COPY test_patch.diff /opt/harbor/test_patch.diff

WORKDIR /testbed
