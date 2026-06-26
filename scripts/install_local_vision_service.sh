#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LLAMA_DIR="${REPO_ROOT}/data/vendor/llama.cpp"
LLAMA_SERVER="${LLAMA_DIR}/build/bin/llama-server"
MODEL_DIR="${REPO_ROOT}/data/models/minicpm-v-4.6"
MODEL_FILE="${MODEL_DIR}/MiniCPM-V-4_6-Q4_K_M.gguf"
MMPROJ_FILE="${MODEL_DIR}/mmproj-model-f16.gguf"
SERVICE_NAME="shortsflow-vision.service"
SERVICE_TEMPLATE="${REPO_ROOT}/deploy/systemd/${SERVICE_NAME}.in"
SERVICE_DST="/etc/systemd/system/${SERVICE_NAME}"
HEALTH_URL="http://127.0.0.1:8081/health"

if ! command -v git >/dev/null 2>&1; then
  echo "missing git" >&2
  exit 1
fi
if ! command -v cmake >/dev/null 2>&1; then
  echo "missing cmake" >&2
  exit 1
fi
if ! command -v curl >/dev/null 2>&1; then
  echo "missing curl" >&2
  exit 1
fi
if [[ ! -f "${SERVICE_TEMPLATE}" ]]; then
  echo "service template not found: ${SERVICE_TEMPLATE}" >&2
  exit 1
fi

mkdir -p "${REPO_ROOT}/data/vendor" "${MODEL_DIR}"

if [[ ! -x "${LLAMA_SERVER}" ]]; then
  if [[ ! -d "${LLAMA_DIR}/.git" ]]; then
    rm -rf "${LLAMA_DIR}"
    git clone --depth 1 https://github.com/ggml-org/llama.cpp "${LLAMA_DIR}"
  fi
  cmake -S "${LLAMA_DIR}" -B "${LLAMA_DIR}/build" \
    -DGGML_NATIVE=OFF \
    -DGGML_CUDA=OFF \
    -DGGML_VULKAN=OFF \
    -DCMAKE_BUILD_TYPE=Release
  cmake --build "${LLAMA_DIR}/build" --target llama-server -j"$(nproc --ignore=1 2>/dev/null || echo 2)"
fi

if [[ ! -s "${MODEL_FILE}" ]]; then
  curl -L -sS --retry 3 --fail -o "${MODEL_FILE}" \
    "https://huggingface.co/openbmb/MiniCPM-V-4.6-GGUF/resolve/main/MiniCPM-V-4_6-Q4_K_M.gguf"
fi
if [[ ! -s "${MMPROJ_FILE}" ]]; then
  curl -L -sS --retry 3 --fail -o "${MMPROJ_FILE}" \
    "https://huggingface.co/openbmb/MiniCPM-V-4.6-GGUF/resolve/main/mmproj-model-f16.gguf"
fi

rendered_service="$(mktemp --suffix=.service)"
trap 'rm -f "${rendered_service}"' EXIT
sed "s|__REPO_ROOT__|${REPO_ROOT}|g" "${SERVICE_TEMPLATE}" > "${rendered_service}"

if command -v systemd-analyze >/dev/null 2>&1; then
  systemd-analyze verify "${rendered_service}"
fi

install -m 0644 "${rendered_service}" "${SERVICE_DST}"
systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

for _ in {1..150}; do
  if curl -fsS "${HEALTH_URL}" 2>/dev/null | grep -q '"status":"ok"'; then
    break
  fi
  sleep 2
done

curl -fsS "${HEALTH_URL}" | grep -q '"status":"ok"'
systemctl --no-pager --full status "${SERVICE_NAME}"
