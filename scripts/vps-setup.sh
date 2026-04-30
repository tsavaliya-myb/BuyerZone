#!/bin/bash
# vps-setup.sh
# Run this ONCE on a fresh Hostinger Ubuntu VPS as root.
# Usage: bash vps-setup.sh

set -euo pipefail

echo "═══════════════════════════════════════════════"
echo " BuyerZone VPS Setup — Hostinger KVM 4"
echo "═══════════════════════════════════════════════"

# ── 1. System update ──────────────────────────────
apt-get update && apt-get upgrade -y
apt-get install -y curl wget git ufw fail2ban

# ── 2. Create deploy user ─────────────────────────
if ! id "deploy" &>/dev/null; then
  adduser --disabled-password --gecos "" deploy
  echo "deploy ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers.d/deploy
  chmod 0440 /etc/sudoers.d/deploy
fi

# ── 3. SSH hardening ──────────────────────────────
sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl restart sshd

# ── 4. Firewall ───────────────────────────────────
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# ── 5. Fail2Ban ───────────────────────────────────
systemctl enable fail2ban
systemctl start fail2ban

# ── 6. Docker ─────────────────────────────────────
if ! command -v docker &>/dev/null; then
  curl -fsSL https://get.docker.com | bash
fi
usermod -aG docker deploy

# ── 7. Nginx + Certbot ────────────────────────────
apt-get install -y nginx certbot python3-certbot-nginx

# ── 8. Swap (safety net for CLIP model loading) ──
if [ ! -f /swapfile ]; then
  fallocate -l 4G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
  sysctl vm.swappiness=10
  echo "vm.swappiness=10" >> /etc/sysctl.conf
fi

# ── 9. App directories ────────────────────────────
mkdir -p /home/deploy/apps /home/deploy/backups
chown -R deploy:deploy /home/deploy/apps /home/deploy/backups

echo ""
echo "✅ VPS setup complete!"
echo ""
echo "Next steps:"
echo "  1. Copy your SSH public key: ssh-copy-id -i ~/.ssh/id_rsa.pub deploy@YOUR_VPS_IP"
echo "  2. Switch to deploy user:    su - deploy"
echo "  3. Clone repo:               git clone https://github.com/YOUR_ORG/BuyerZone.git ~/apps/BuyerZone"
echo "  4. Fill .env:                cp .env.example .env && nano .env"
echo "  5. Configure Nginx:          see deployment_plan.md Phase 3"
echo "  6. Get SSL:                  certbot --nginx -d api.yourdomain.com"
