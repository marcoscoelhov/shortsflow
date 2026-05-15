#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="yts-render-hub.service"
SERVICE_TEMPLATE="${REPO_ROOT}/deploy/systemd/${SERVICE_NAME}.in"
SERVICE_DST="/etc/systemd/system/${SERVICE_NAME}"
HEALTH_URL="http://127.0.0.1:8080/healthz"

if [[ ! -f "${SERVICE_TEMPLATE}" ]]; then
  echo "service template not found: ${SERVICE_TEMPLATE}" >&2
  exit 1
fi

if [[ ! -x "${REPO_ROOT}/.venv/bin/python" ]]; then
  echo "missing venv python: ${REPO_ROOT}/.venv/bin/python" >&2
  exit 1
fi

rendered_service="$(mktemp --suffix=.service)"
trap 'rm -f "${rendered_service}"' EXIT

sed "s|__REPO_ROOT__|${REPO_ROOT}|g" "${SERVICE_TEMPLATE}" > "${rendered_service}"

if command -v systemd-analyze >/dev/null 2>&1; then
  systemd-analyze verify "${rendered_service}"
fi

install -m 0644 "${rendered_service}" "${SERVICE_DST}"
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

for _ in {1..60}; do
  if curl -fsS "${HEALTH_URL}" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

curl -fsS "${HEALTH_URL}" >/dev/null
systemctl --no-pager --full status "${SERVICE_NAME}"
