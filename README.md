# Monolith

Monolith is a script and python package for creating monolithic Dockerfiles and
for generating Singularity definition files from Dockerfiles.


## Installation
The two requirements of to run the script are `requests` and `BeautifulSoup`.

```
pip install requests beautifulsoup4
```
or
```
pip install -r requirements.txt
```


## Usage
Simply pass in the image name in the form "user/image".
The script will write it out to a file named `Monolith.txt` by default.
To change that, set the `-f` or `--file` parameter.

```
monolith.py jupyterhub/jupyterhub
```

## Singularity Definition File
You can use monolith to create a dingularity file. To do so, pass the
`--make-singularity` flag. It will then create an equivalent singularity file
from the dockerfile.

You can also pass in `--singularity-bootstrap` and `--singularity-from` to set
the Singularity definition files `Bootstrap` and `From` field.


## Notes
* This does not grab the exact dockerfile that was used, just the one that is available on dockerhub.
* Tags are currently ignored.


## Sample Output
```
./monolith.py kaixhin/cuda-caffe
```

```
### nvidia/cuda:7.0-cudnn4-devel --- 2017-03-03 16:48:10.751460
### kaixhin/cuda-caffe-deps:8.0 --- 2017-03-03 16:48:10.345190
# Start with cuDNN base image
FROM nvidia/cuda:7.0-cudnn4-devel
MAINTAINER Kai Arulkumaran <design@kaixhin.com>

# Install git, wget, bc and dependencies
RUN apt-get update && apt-get install -y \
  git \
  wget \
  bc \
  cmake \
  libatlas-base-dev \
  libatlas-dev \
  libboost-all-dev \
  libopencv-dev \
  libprotobuf-dev \
  libgoogle-glog-dev \
  libgflags-dev \
  protobuf-compiler \
  libhdf5-dev \
  libleveldb-dev \
  liblmdb-dev \
  libsnappy-dev \
  python-dev \
  python-pip \
  python-numpy \
  gfortran > /dev/null
# Clone Caffe repo and move into it
RUN cd /root && git clone https://github.com/BVLC/caffe.git && cd caffe && \
# Install python dependencies
  cat python/requirements.txt | xargs -n1 pip install
### kaixhin/cuda-caffe --- 2017-03-03 16:48:09.807827
# Start with CUDA Caffe dependencies
FROM kaixhin/cuda-caffe-deps:8.0
MAINTAINER Kai Arulkumaran <design@kaixhin.com>

# Move into Caffe repo
RUN cd /root/caffe && \
# Make and move into build directory
  mkdir build && cd build && \
# CMake
  cmake .. && \
# Make
  make -j"$(nproc)" all && \
  make install

# Add to Python path
ENV PYTHONPATH=/root/caffe/python:$PYTHONPATH

# Set ~/caffe as working directory
WORKDIR /root/caffe
```

