#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
runtime_dir="${project_root}/runtime/gvhmr-env"
worker_image="${GVHMR_BOOTSTRAP_IMAGE:-elderly-ai-platform-fall-risk-worker}"
pip_index="${PIP_INDEX_URL:-https://pypi.org/simple}"
debian_mirror="${DEBIAN_MIRROR:-http://deb.debian.org/debian}"
debian_security_mirror="${DEBIAN_SECURITY_MIRROR:-http://deb.debian.org/debian-security}"
host_uid="$(id -u)"
host_gid="$(id -g)"

mkdir -p "${runtime_dir}"

docker run --rm \
  --user 0:0 \
  -e PIP_INDEX_URL="${pip_index}" \
  -e DEBIAN_MIRROR="${debian_mirror}" \
  -e DEBIAN_SECURITY_MIRROR="${debian_security_mirror}" \
  -e HOST_UID="${host_uid}" \
  -e HOST_GID="${host_gid}" \
  -v "${runtime_dir}:/runtime/gvhmr-env" \
  -v "${project_root}/fall-risk-worker/vendor:/opt/gvhmr-wheels:ro" \
  -v "${project_root}/fall-risk-worker/pipelines/gvhmr/requirements.txt:/tmp/gvhmr-requirements.txt:ro" \
  -v "${project_root}/third_party/GVHMR:/opt/gvhmr:ro" \
  "${worker_image}" \
  /bin/sh -ec '
    sed -i \
      -e "s|http://deb.debian.org/debian-security|${DEBIAN_SECURITY_MIRROR}|g" \
      -e "s|http://deb.debian.org/debian|${DEBIAN_MIRROR}|g" \
      /etc/apt/sources.list.d/debian.sources
    apt-get update
    apt-get install -y --no-install-recommends build-essential
    rm -rf /var/lib/apt/lists/*
    mkdir -p /runtime/gvhmr-env/.tmp
    export TMPDIR=/runtime/gvhmr-env/.tmp
    if [ ! -x /runtime/gvhmr-env/bin/python ]; then
      python -m venv /runtime/gvhmr-env
    fi
    /runtime/gvhmr-env/bin/pip install --no-cache-dir \
      /opt/gvhmr-wheels/torch-2.3.0+cu121-cp310-cp310-linux_x86_64.whl \
      /opt/gvhmr-wheels/torchvision-0.18.0+cu121-cp310-cp310-linux_x86_64.whl
    /runtime/gvhmr-env/bin/pip install --no-cache-dir \
      --index-url "${PIP_INDEX_URL}" \
      --find-links /opt/gvhmr-wheels \
      -r /tmp/gvhmr-requirements.txt
    printf "%s\n" /opt/gvhmr > /runtime/gvhmr-env/lib/python3.10/site-packages/gvhmr-source.pth
    chown -R "${HOST_UID}:${HOST_GID}" /runtime/gvhmr-env
  '

echo "GVHMR runtime created at ${runtime_dir}"
