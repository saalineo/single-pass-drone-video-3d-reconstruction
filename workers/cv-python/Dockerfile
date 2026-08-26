# syntax=docker/dockerfile:1.7
FROM nvidia/cuda:12.4.1-devel-ubuntu22.04 AS builder

ARG COLMAP_VERSION=3.9.1
ARG CERES_VERSION=2.2.0
# Covers: Jetson Orin (8.7), edge RTX 4000-class (7.5 Turing or 8.9 Ada depending on
# generation), core L40S (8.9). Building all four keeps one image portable across every
# plane per architect/06 §1 / architect/07 §2's "same Helm chart" rule; it costs ~15 extra
# minutes of nvcc compile time, paid once in CI, not per deploy.
ARG CUDA_ARCHS="75;80;86;87;89"

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake ninja-build git ca-certificates \
    libboost-program-options-dev libboost-graph-dev libboost-system-dev \
    libeigen3-dev libflann-dev libfreeimage-dev libmetis-dev \
    libgoogle-glog-dev libgtest-dev libsqlite3-dev libglew-dev \
    qtbase5-dev libqt5opengl5-dev libcgal-dev libcgal-qt5-dev \
    libatlas-base-dev libsuitesparse-dev python3.11 python3.11-dev python3-pip \
    && rm -rf /var/lib/apt/lists/*

# --- Ceres Solver, built from source and version-pinned rather than the apt package,
# which on Ubuntu 22.04 ships 2.0.0 and lacks fixes COLMAP 3.9's BA relies on.
WORKDIR /opt/build
RUN git clone --branch ${CERES_VERSION} --depth 1 https://github.com/ceres-solver/ceres-solver.git \
    && cmake -S ceres-solver -B ceres-solver/build -GNinja \
        -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF -DBUILD_EXAMPLES=OFF \
    && cmake --build ceres-solver/build --target install -j"$(nproc)"

# --- COLMAP itself, CUDA feature extraction enabled explicitly.
RUN git clone --branch ${COLMAP_VERSION} --depth 1 https://github.com/colmap/colmap.git \
    && cmake -S colmap -B colmap/build -GNinja \
        -DCMAKE_BUILD_TYPE=Release \
        -DCUDA_ENABLED=ON \
        -DCMAKE_CUDA_ARCHITECTURES="${CUDA_ARCHS}" \
        -DGUI_ENABLED=OFF \
    && cmake --build colmap/build --target install -j"$(nproc)"

# --- pycolmap, built from the SAME checkout against the SAME installed libs — this is the
# whole reason we don't `pip install pycolmap` from PyPI: that wheel is built against its
# own bundled COLMAP snapshot and CUDA toolkit version, and mixing it with a differently
# -built libcolmap.so at runtime is an ABI hazard (crashes or silent CPU fallback).
ENV POETRY_VIRTUALENVS_CREATE=false
RUN python3.11 -m pip install --no-cache-dir "pycolmap==0.6.1" \
        --no-binary pycolmap \
        --config-settings=cmake.define.CMAKE_CUDA_ARCHITECTURES="${CUDA_ARCHS}" \
    || (cd colmap/pycolmap && python3.11 -m pip install --no-cache-dir .)

FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04 AS runtime

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 python3-pip ffmpeg \
    libgomp1 libqt5core5a libqt5gui5 libgl1 libglew2.2 \
    libboost-program-options1.74.0 libboost-graph1.74.0 libboost-system1.74.0 \
    libfreeimage3 libmetis5 libgoogle-glog0v5 libceres3 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib /usr/local/lib
COPY --from=builder /usr/local/bin/colmap /usr/local/bin/colmap
COPY --from=builder /usr/local/lib/python3.11/dist-packages /usr/local/lib/python3.11/dist-packages
RUN ldconfig

ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility
ENV POETRY_VIRTUALENVS_CREATE=false

WORKDIR /app
COPY pyproject.toml poetry.lock ./
RUN python3.11 -m pip install --no-cache-dir poetry==1.8.3 \
    && poetry install --no-root --only main

COPY . .
CMD ["python3.11", "worker.py"]
