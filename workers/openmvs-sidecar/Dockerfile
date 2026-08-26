FROM nvidia/cuda:12.1.1-devel-ubuntu22.04
RUN apt-get update && apt-get install -y cmake libeigen3-dev libceres-dev libcgal-dev \
    libboost-all-dev libopencv-dev git python3 python3-pip
RUN git clone --branch v2.3.0 https://github.com/cdcseacave/openMVS.git /src/openmvs \
    && cmake -S /src/openmvs -B /build -DCMAKE_BUILD_TYPE=Release -DOpenMVS_USE_CUDA=ON \
    && cmake --build /build -j"$(nproc)" --target install

RUN pip3 install grpcio grpcio-tools

COPY server.py /app/server.py
ENTRYPOINT ["python3", "/app/server.py"]
