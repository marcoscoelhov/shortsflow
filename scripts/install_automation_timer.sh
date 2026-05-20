#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="yts-render-automation.service"
TIMER_NAME="yts-render-automation.timer"
SERVICE_TEMPLATE="${REPO_ROOT}/deploy/systemd/${SERVICE_NAME}.in"
TIMER_TEMPLATE="${REPO_ROOT}/deploy/systemd/${TIMER_NAME}.in"
SERVICE_DST="/etc/systemd/system/${SERVICE_NAME}"
TIMER_DST="/etc/systemd/system/${TIMER_NAME}"

if [[ ! -x "${REPO_ROOT}/.venv/bin/python" ]]; then
  echo "missing venv python: ${REPO_ROOT}/.venv/bin/python" >&2
  exit 1
fi

for template in "${SERVICE_TEMPLATE}" "${TIMER_TEMPLATE}"; do
  if [[ ! -f "${template}" ]]; then
    echo "template not found: ${template}" >&2
    exit 1
  fi
done

rendered_service="$(mktemp --suffix=.service)"
rendered_timer="$(mktemp --suffix=.timer)"
trap 'rm -f "${rendered_service}" "${rendered_timer}"' EXIT

sed "s|__REPO_ROOT__|${REPO_ROOT}|g" "${SERVICE_TEMPLATE}" > "${rendered_service}"
sed "s|__REPO_ROOT__|${REPO_ROOT}|g" "${TIMER_TEMPLATE}" > "${rendered_timer}"

if command -v systemd-analyze >/dev/null 2>&1; then
  systemd-analyze verify "${rendered_service}" "${rendered_timer}"
fi

install -m 0644 "${rendered_service}" "${SERVICE_DST}"
install -m 0644 "${rendered_timer}" "${TIMER_DST}"
systemctl daemon-reload
systemctl enable --now "${TIMER_NAME}"
systemctl --no-pager --full status "${TIMER_NAME}"
