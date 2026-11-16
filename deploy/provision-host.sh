#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "run this script as root" >&2
  exit 77
fi

repository_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
systemctl_path=$(command -v systemctl)

if ! getent group huddle >/dev/null; then
  groupadd --system huddle
fi

if ! id huddle >/dev/null 2>&1; then
  useradd \
    --system \
    --gid huddle \
    --home-dir /var/lib/huddle-app \
    --shell /usr/sbin/nologin \
    huddle
fi

for runner_account in huddle-ci huddle-deploy; do
  if ! id "$runner_account" >/dev/null 2>&1; then
    useradd \
      --system \
      --create-home \
      --shell /bin/bash \
      "$runner_account"
  fi
done

usermod --append --groups huddle huddle-deploy

install -d -o huddle-deploy -g huddle -m 2770 /opt/huddle-app
install -d -o huddle-deploy -g huddle -m 2770 /opt/huddle-app/releases
install -d -o huddle -g huddle -m 2770 /var/lib/huddle-app
install -d -o huddle-deploy -g huddle -m 2770 /var/backups/huddle-app
install -d -o huddle-ci -g huddle-ci -m 0750 /opt/actions-runner-ci
install -d -o huddle-deploy -g huddle-deploy -m 0750 /opt/actions-runner-deploy

install \
  -o root \
  -g root \
  -m 0755 \
  "$repository_root/deploy/deploy-huddle-app" \
  /usr/local/sbin/deploy-huddle-app

install \
  -o root \
  -g root \
  -m 0644 \
  "$repository_root/deploy/huddle-app.service" \
  /etc/systemd/system/huddle-app.service

cat >/etc/sudoers.d/huddle-deploy <<EOF
huddle-deploy ALL=(root) NOPASSWD: \
  $systemctl_path start huddle-app.service, \
  $systemctl_path stop huddle-app.service, \
  $systemctl_path restart huddle-app.service
EOF
chmod 0440 /etc/sudoers.d/huddle-deploy
visudo --check --file=/etc/sudoers.d/huddle-deploy

systemctl daemon-reload
systemctl enable huddle-app.service

cat <<'EOF'
Host directories, accounts, deployment command, and systemd unit are installed.

Next:
  1. Register /opt/actions-runner-ci as user huddle-ci with label huddle-ci.
  2. Register /opt/actions-runner-deploy as user huddle-deploy with label huddle-deploy.
  3. Install each runner as a service.
  4. Push application code and dependency locks before expecting a deployment.
EOF
