#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
user_home="$(getent passwd "$(id -un)" | cut -d: -f6)"

for command in git gh tailscale curl python3.12; do
  command -v "${command}" >/dev/null 2>&1 || { echo "missing command: ${command}" >&2; exit 1; }
done

gh auth status >/dev/null
tailscale status >/dev/null

if [[ ! -x "${repo_root}/.venv/bin/python" ]]; then
  python3.12 -m venv --without-pip "${repo_root}/.venv"
fi
python3.12 -m pip --python "${repo_root}/.venv/bin/python" install -e "${repo_root}[dev]"

install -d -m 0755 "${user_home}/.local/bin"
ln -sfn "${repo_root}/.venv/bin/shortsflow" "${user_home}/.local/bin/shortsflow"

skill_source="${repo_root}/.agents/skills/remote-vps-runtime"
if [[ -d "${skill_source}" ]]; then
  install -d -m 0755 "${user_home}/.codex/skills"
  ln -sfn "${skill_source}" "${user_home}/.codex/skills/remote-vps-runtime"
fi

production_health="$(curl --fail --silent --show-error https://srv769897.tailc97b69.ts.net/healthz)"
staging_health="$(curl --fail --silent --show-error https://srv769897.tailc97b69.ts.net:8443/healthz)"
PRODUCTION_HEALTH="${production_health}" STAGING_HEALTH="${staging_health}" "${repo_root}/.venv/bin/python" - <<'PY'
import json
import os

expected = {
    "production": json.loads(os.environ["PRODUCTION_HEALTH"]),
    "staging": json.loads(os.environ["STAGING_HEALTH"]),
}
for name, payload in expected.items():
    runtime = payload.get("runtime") or {}
    if runtime.get("environment") != name:
        raise SystemExit(f"unexpected {name} runtime identity: {runtime}")
    print(f"{name}: {runtime.get('revision')} ready")
PY

echo "remote client ready; ensure ${user_home}/.local/bin is on PATH"
