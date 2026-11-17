#!/usr/bin/env bash
# ব্যবহার:
#   bash deploy.sh          প্রথমবার ইনস্টল (Ubuntu সার্ভারে)
#   bash deploy.sh update   GitHub থেকে নতুন কোড এনে রিস্টার্ট
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_USER="$(id -un)"
DATA_DIR="${HOME}/bot_data"
SERVICE="filebot"
PY="${APP_DIR}/venv/bin/python"
ENV_FILE="${APP_DIR}/.env"

if [ "$(id -u)" -eq 0 ]; then
  echo "❌ root দিয়ে চালাবেন না। সাধারণ ইউজার (যেমন ubuntu) দিয়ে চালান।"
  exit 1
fi

if [ "${1:-}" = "update" ]; then
  cd "$APP_DIR"
  git pull
  "${APP_DIR}/venv/bin/pip" install -r requirements.txt
  sudo systemctl restart "$SERVICE"
  sleep 3
  sudo systemctl status "$SERVICE" --no-pager || true
  echo "✅ আপডেট শেষ।"
  exit 0
fi

echo "📦 সিস্টেম প্যাকেজ ইনস্টল হচ্ছে..."
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip git nano

echo "🐍 পাইথন পরিবেশ তৈরি হচ্ছে..."
python3 -m venv "${APP_DIR}/venv"
"${APP_DIR}/venv/bin/pip" install --upgrade pip
"${APP_DIR}/venv/bin/pip" install -r "${APP_DIR}/requirements.txt"

mkdir -p "$DATA_DIR"
chmod 700 "$DATA_DIR"

if [ ! -f "$ENV_FILE" ]; then
  echo
  echo "🔑 এখন গোপন তথ্য দিন (টাইপ করার সময় টোকেন স্ক্রিনে দেখাবে না)।"
  read -r -s -p "BOT_TOKEN পেস্ট করুন: " BOT_TOKEN
  echo
  read -r -p "ADMIN_ID (সংখ্যা): " ADMIN_ID

  if [[ ! "$BOT_TOKEN" =~ ^[0-9]+:[A-Za-z0-9_-]+$ ]]; then
    echo "❌ টোকেনের ফরম্যাট ঠিক নয়। আবার চালান।"
    exit 1
  fi
  if [[ ! "$ADMIN_ID" =~ ^[0-9]+$ ]]; then
    echo "❌ ADMIN_ID শুধু সংখ্যা হতে হবে। আবার চালান।"
    exit 1
  fi

  (
    umask 077
    printf 'BOT_TOKEN=%s\nADMIN_ID=%s\nDATA_DIR=%s\nMAX_FILE_MB=20\nBACKUP_KEEP=14\nGOOGLE_SERVICE_ACCOUNT_FILE=\nLOG_LEVEL=INFO\n' \
      "$BOT_TOKEN" "$ADMIN_ID" "$DATA_DIR" > "$ENV_FILE"
  )
  chmod 600 "$ENV_FILE"
  echo "✅ .env ফাইল তৈরি হয়েছে।"
else
  echo "ℹ️ .env আগে থেকেই আছে, ওটাই ব্যবহার হবে।"
  chmod 600 "$ENV_FILE"
fi

echo "🔍 কনফিগ পরীক্ষা হচ্ছে..."
cd "$APP_DIR"
"$PY" -c "from config import load_config; c = load_config(); print('✅ কনফিগ ঠিক আছে। ADMIN_ID =', c.admin_id)"

echo "⚙️ systemd সার্ভিস তৈরি হচ্ছে..."
sudo tee "/etc/systemd/system/${SERVICE}.service" > /dev/null <<EOF
[Unit]
Description=Telegram File Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${APP_USER}
WorkingDirectory=${APP_DIR}
Environment=PYTHONUNBUFFERED=1
ExecStart=${PY} bot.py
Restart=always
RestartSec=5
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now "$SERVICE"
sleep 3
sudo systemctl status "$SERVICE" --no-pager || true

echo
echo "🎉 শেষ! Telegram-এ আপনার বটে /start দিন।"
echo "লাইভ লগ দেখতে:  sudo journalctl -u ${SERVICE} -f"
