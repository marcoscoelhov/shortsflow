#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "run as root" >&2
  exit 1
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_env="${SHORTSFLOW_SOURCE_ENV:-${repo_root}/.env}"

for command in git npm python3.12 rsync systemctl systemd-tmpfiles tailscale visudo; do
  command -v "${command}" >/dev/null 2>&1 || { echo "missing command: ${command}" >&2; exit 1; }
done

if [[ ! -f "${source_env}" ]]; then
  echo "missing provider configuration: ${source_env}" >&2
  exit 1
fi

getent group shortsflow >/dev/null 2>&1 || groupadd --system shortsflow
for environment in production staging; do
  runtime_user="shortsflow-${environment}"
  id "${runtime_user}" >/dev/null 2>&1 || useradd --system --home-dir "/var/lib/${runtime_user}" --create-home --shell /usr/sbin/nologin "${runtime_user}"
  usermod --append --groups shortsflow "${runtime_user}"
done
id deploy-staging >/dev/null 2>&1 || useradd --create-home --shell /bin/bash deploy-staging
id deploy >/dev/null 2>&1 || useradd --create-home --shell /bin/bash deploy
usermod --append --groups shortsflow deploy-staging
usermod --append --groups shortsflow deploy

install -d -m 0755 /opt/shortsflow/production/releases /opt/shortsflow/staging/releases
install -d -m 0750 -o shortsflow-production -g shortsflow-production /srv/shortsflow/production/data /var/backups/shortsflow/production
install -d -m 0750 -o shortsflow-staging -g shortsflow-staging /srv/shortsflow/staging/data /var/backups/shortsflow/staging
install -d -m 0755 -o root -g root /etc/shortsflow

install -m 0755 "${repo_root}/scripts/remote_deploy.py" /usr/local/sbin/shortsflow-deploy
install -m 0755 "${repo_root}/scripts/runtime_backup.py" /usr/local/sbin/shortsflow-backup
install -m 0644 "${repo_root}/deploy/systemd/shortsflow-production.service" /etc/systemd/system/shortsflow-production.service
install -m 0644 "${repo_root}/deploy/systemd/shortsflow-staging.service" /etc/systemd/system/shortsflow-staging.service
install -m 0644 "${repo_root}/deploy/systemd/shortsflow-backup@.service" /etc/systemd/system/shortsflow-backup@.service
install -m 0644 "${repo_root}/deploy/systemd/shortsflow-backup@.timer" /etc/systemd/system/shortsflow-backup@.timer
install -m 0644 "${repo_root}/deploy/systemd/shortsflow-backup-weekly@.service" /etc/systemd/system/shortsflow-backup-weekly@.service
install -m 0644 "${repo_root}/deploy/systemd/shortsflow-backup-weekly@.timer" /etc/systemd/system/shortsflow-backup-weekly@.timer
install -m 0644 "${repo_root}/deploy/systemd/shortsflow-tmpfiles.conf" /usr/lib/tmpfiles.d/shortsflow.conf
systemd-tmpfiles --create /usr/lib/tmpfiles.d/shortsflow.conf

if [[ ! -f /etc/shortsflow/production.env ]]; then
  install -m 0640 -o root -g shortsflow-production "${source_env}" /etc/shortsflow/production.env
fi
if [[ ! -f /etc/shortsflow/staging.env ]]; then
  install -m 0640 -o root -g shortsflow-staging "${source_env}" /etc/shortsflow/staging.env
fi

if [[ ! -f /etc/shortsflow/production-release.env ]]; then
  install -m 0640 -o root -g shortsflow-production /dev/null /etc/shortsflow/production-release.env
fi
if [[ ! -f /etc/shortsflow/staging-release.env ]]; then
  install -m 0640 -o root -g shortsflow-staging /dev/null /etc/shortsflow/staging-release.env
fi

sudoers_file="$(mktemp)"
trap 'rm -f "${sudoers_file}"' EXIT
{
  echo 'deploy-staging ALL=(root) NOPASSWD: /usr/local/sbin/shortsflow-deploy staging *'
  echo 'deploy ALL=(root) NOPASSWD: /usr/local/sbin/shortsflow-deploy production *'
} > "${sudoers_file}"
visudo -cf "${sudoers_file}"
install -m 0440 "${sudoers_file}" /etc/sudoers.d/shortsflow-deploy

systemctl daemon-reload
systemctl enable shortsflow-staging.service
systemctl enable --now shortsflow-backup@production.timer shortsflow-backup@staging.timer
systemctl enable --now shortsflow-backup-weekly@production.timer shortsflow-backup-weekly@staging.timer
tailscale set --ssh
tailscale serve --bg --https=8443 --yes http://127.0.0.1:8082

echo "remote runtime prerequisites installed"
echo "deploy staging with: sudo -u deploy-staging sudo /usr/local/sbin/shortsflow-deploy staging <full-sha>"
echo "production remains on the existing service until staging is approved"
