# 📥 Telegram Excel Collection & Buyer Delivery Bot

অনুমোদিত ব্যবহারকারীদের কাছ থেকে Excel (.xlsx) ও Google Sheets সংগ্রহ করে, অ্যাডমিনের নিশ্চিতকরণের পর ক্রেতাদের কাছে পাঠানোর বট।

> 🔒 এই বট ডকুমেন্ট সংগ্রহের টুল। পাসওয়ার্ড, কুকি, টোকেন, OTP, 2FA বা রিকভারি কোড আছে এমন ফাইল স্বয়ংক্রিয়ভাবে বাতিল হয়।

## ১. কী কী কাজ করে

- শুধু অনুমোদিত ব্যবহারকারী `.xlsx` বা Google Sheets লিংক জমা দিতে পারে
- প্রতিটি ফাইলের ইউনিক ID (#1001, #1002…), ডুপ্লিকেট ফাইল বাতিল
- নতুন ফাইল এলে অ্যাডমিনের কাছে সঙ্গে সঙ্গে নোটিফিকেশন
- ইনলাইন-বোতামের অ্যাডমিন ড্যাশবোর্ড
- ক্রেতা নিবন্ধন একবার-ব্যবহারযোগ্য লিংকে (যাচাইকৃত Chat ID, ইউজারনেমে নির্ভর নেই)
- ডেলিভারি অ্যাডমিনের কনফার্মেশন ছাড়া হয় না। Telegram নিশ্চিত না করলে "সফল" ধরা হয় না
- ডেলিভারি ইতিহাস, ডুপ্লিকেট ডেলিভারি সতর্কতা, Retry ও Cancel বোতাম
- প্রতিদিন স্বয়ংক্রিয় ডাটাবেস ব্যাকআপ

## ২. প্রজেক্টের ফাইল

```
bot.py  config.py  database.py  check_connection.py  deploy.sh
requirements.txt  .env.example  .gitignore  pytest.ini  README.md
handlers/   __init__.py admin.py buyer.py common.py delivery.py submitter.py
services/   __init__.py file_service.py google_sheets.py notification.py
keyboards/  __init__.py admin_keyboard.py user_keyboard.py
tests/      __init__.py conftest.py test_auth.py test_file_validation.py
            test_database.py test_delivery.py test_submission.py
```

## ৩. BotFather থেকে বট বানানো

1. Telegram-এ **@BotFather** খুলুন (নীল টিক থাকা)।
2. `/newbot` পাঠান → বটের নাম দিন → ইউজারনেম দিন (শেষে `bot` থাকতে হবে)।
3. যে **টোকেন** দেবে (`123456789:ABC...`) সেটি কপি করে রাখুন।
4. ঐচ্ছিক: `/mybots` → আপনার বট → **Bot Settings → Allow Groups?** → **Turn off**।
5. আপনার বটে গিয়ে নিজে **Start** চাপুন।

> ⚠️ টোকেন কাউকে দেবেন না, GitHub-এ তুলবেন না। ফাঁস হলে BotFather-এ `/revoke` দিয়ে নতুন টোকেন নিন।

## ৪. আপনার Admin ID

Telegram-এ **@userinfobot** খুলে Start চাপুন। `Id:` এর পাশের সংখ্যাটিই Admin ID।

## ৫. GitHub-এ কোড তোলা (মোবাইল ব্রাউজারে)

1. github.com-এ সাইন ইন করুন → **New repository** → নাম দিন (যেমন `telegram_file_bot`)।
2. রিপো **Public** রাখলে সবচেয়ে সহজ। কোডে কোনো গোপন তথ্য নেই, গোপন তথ্য থাকে শুধু সার্ভারের `.env`-এ।
3. **Add file → Create new file**। নামের ঘরে পুরো পথ লিখুন (যেমন `handlers/admin.py`, `/` লিখলে ফোল্ডার বানায়), কোড পেস্ট করুন, **Commit changes**।
4. ⚠️ **`.env` ফাইল কখনও আপলোড করবেন না।** শুধু `.env.example` আপলোড করবেন।
5. ব্রাউজারে সুবিধা না হলে ⋮ মেনু থেকে **Desktop site** চালু করুন।

## ৬. ফোনে Termux-এ পরীক্ষা চালানো (ঐচ্ছিক)

1. **F-Droid** (f-droid.org) থেকে **Termux** নামান। Play Store-এরটা নেবেন না।
2. Termux-এ এক এক করে পেস্ট করুন:

```bash
pkg update -y && pkg upgrade -y
pkg install -y python git nano openssh
git clone https://github.com/আপনার_ইউজারনেম/আপনার_রিপো.git telegram_file_bot
cd telegram_file_bot
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
```

3. `nano`-তে `BOT_TOKEN=` ও `ADMIN_ID=` বসান (`=` এর দুই পাশে স্পেস বা উদ্ধৃতিচিহ্ন নয়)। সেভ: **CTRL+O**, Enter। বের হওয়া: **CTRL+X**।
4. সংযোগ পরীক্ষা: `python check_connection.py`
5. বট চালান: `python bot.py` (বন্ধ করতে **CTRL+C**)।

ফোনে চালালে ফোন বা Termux বন্ধ হলে বটও বন্ধ হয়। ২৪/৭ চালাতে নিচের সার্ভার ধাপ লাগবে।

## ৭. বিনামূল্যে ২৪/৭ হোস্টিং: Oracle Cloud Always Free

### সৎ সীমাবদ্ধতা (আগে পড়ুন)

- সাইন-আপে **কার্ড যাচাই** লাগে। Oracle বলে Always Free ব্যবহারে চার্জ হয় না। কিন্তু কার্ড ছাড়া হবে না।
- Oracle ২০২৬ সালে Arm ফ্রি সীমা কমিয়েছে। আমাদের বট হালকা, তাই ১টি AMD Micro (1 GB RAM) যথেষ্ট।
- কোনো অঞ্চলে ফ্রি মেশিনের ক্যাপাসিটি না-ও থাকতে পারে। তখন পরে আবার চেষ্টা করুন বা অন্য Availability Domain বেছে নিন।
- অলস Always Free মেশিন Oracle বন্ধ বা পুনরুদ্ধার করতে পারে। এর বর্তমান সঠিক নিয়ম আমি যাচাই করতে পারিনি, Oracle-এর ডকুমেন্টেশনের "Always Free resources" অংশ দেখে নেবেন। বন্ধ হলে কনসোল থেকে **Start** করা যায়।
- **কখনও "Upgrade to Paid / Pay As You Go" চালু করবেন না।**

### ধাপ ১: অ্যাকাউন্ট খোলা
ব্রাউজারে `oracle.com/cloud/free` → **Start for free** → তথ্য ও কার্ড দিন। হোম রিজিয়ন একবার বাছলে বদলানো যায় না।

### ধাপ ২: ফোনে SSH কী বানানো (Termux-এ)
```bash
ssh-keygen -t ed25519 -f ~/.ssh/oracle_key -N ""
cat ~/.ssh/oracle_key.pub
```
`ssh-ed25519 AAAA...` দিয়ে শুরু হওয়া লাইনটি লং-প্রেস করে কপি করুন। এটি পাবলিক কী, দেখানো নিরাপদ। প্রাইভেট কী (`oracle_key`) কাউকে দেবেন না।

### ধাপ ৩: ভার্চুয়াল মেশিন বানানো
1. Oracle কনসোল → **Compute → Instances → Create instance**।
2. **Image:** Canonical Ubuntu (22.04 বা 24.04)।
3. **Shape:** `VM.Standard.E2.1.Micro` বেছে নিন, **"Always Free-eligible"** লেখা আছে কি না দেখুন।
4. **Networking:** Public IPv4 address **Assign** থাকতে হবে।
5. **Add SSH keys → Paste public keys** এ ধাপ ২-এর পাবলিক কী পেস্ট করুন।
6. **Create** চাপুন। কিছুক্ষণে Running হলে **Public IP address** টুকে রাখুন।
7. ক্যাপাসিটি-ত্রুটি এলে পরে আবার চেষ্টা করুন।

### ধাপ ৪: সার্ভারে ঢোকা (Termux থেকে)
```bash
ssh -i ~/.ssh/oracle_key ubuntu@আপনার_PUBLIC_IP
```
প্রথমবার `yes` লিখুন। বের হতে `exit`।

### ধাপ ৫ (সহজ পথ): এক কমান্ডে সেটআপ, `deploy.sh` দিয়ে

সার্ভারের ভেতরে:
```bash
sudo apt-get update -y && sudo apt-get install -y git
git clone https://github.com/আপনার_ইউজারনেম/আপনার_রিপো.git telegram_file_bot
cd telegram_file_bot
bash deploy.sh
```
স্ক্রিপ্ট নিজে সব ইনস্টল করবে, তারপর `BOT_TOKEN` ও `ADMIN_ID` চাইবে (টোকেন টাইপ করার সময় স্ক্রিনে দেখা যাবে না, পেস্ট করে Enter দিন)। শেষে systemd সার্ভিস চালু করে দেবে। Telegram-এ আপনার বটে `/start` দিন।

পরে কোড বদলালে: `cd ~/telegram_file_bot && bash deploy.sh update`

### ধাপ ৫ (বিকল্প): হাতে হাতে সেটআপ

`deploy.sh` কাজ না করলে এই পথে যান।

```bash
sudo apt update && sudo apt -y upgrade
sudo apt install -y python3 python3-venv python3-pip git nano
git clone https://github.com/আপনার_ইউজারনেম/আপনার_রিপো.git telegram_file_bot
cd telegram_file_bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
mkdir -p /home/ubuntu/bot_data
cp .env.example .env
nano .env
chmod 600 .env
```

`.env`-এ এভাবে বসান। `DATA_DIR` কোড-ফোল্ডারের বাইরে রাখা হচ্ছে, তাই আপডেটে ডেটা হারাবে না:

```text
BOT_TOKEN=আপনার_টোকেন
ADMIN_ID=আপনার_সংখ্যা
DATA_DIR=/home/ubuntu/bot_data
MAX_FILE_MB=20
BACKUP_KEEP=14
GOOGLE_SERVICE_ACCOUNT_FILE=
LOG_LEVEL=INFO
```

দ্রুত পরীক্ষা (সফল হলে Telegram-এ বার্তা আসবে): `python check_connection.py`

তারপর systemd সার্ভিস (ক্র্যাশ হলে নিজে চালু হবে, রিবুটের পরও চলবে):
```bash
sudo tee /etc/systemd/system/filebot.service > /dev/null <<'EOF'
[Unit]
Description=Telegram File Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/telegram_file_bot
ExecStart=/home/ubuntu/telegram_file_bot/venv/bin/python bot.py
Restart=always
RestartSec=5
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now filebot
sudo systemctl status filebot --no-pager
```
`active (running)` দেখালে সফল।

### দরকারি কমান্ড
| কাজ | কমান্ড |
|---|---|
| অবস্থা দেখা | `sudo systemctl status filebot --no-pager` |
| লাইভ লগ | `sudo journalctl -u filebot -f` (বের হতে CTRL+C) |
| রিস্টার্ট | `sudo systemctl restart filebot` |
| বন্ধ | `sudo systemctl stop filebot` |
| বট লগ ফাইল | `tail -n 50 ~/bot_data/logs/bot.log` |

### কোড আপডেট করার নিয়ম
GitHub-এ ফাইল বদলে সার্ভারে: `cd ~/telegram_file_bot && bash deploy.sh update`

ডাটাবেস ও ফাইল `DATA_DIR`-এ থাকে, তাই আপডেট বা রিস্টার্টে মোছে না।

## ৮. বট ব্যবহারের নিয়ম

**অ্যাডমিন (আপনি):** বটে `/start` বা `/admin` দিলে ড্যাশবোর্ড আসবে।

| কমান্ড | কাজ |
|---|---|
| `/approve ID` | সাবমিটার অনুমোদন |
| `/remove ID` | সাবমিটার বাদ |
| `/users` | অনুমোদিত তালিকা ও Access Request |
| `/pending` | অপেক্ষমাণ ফাইল |
| `/files` | সব ফাইল |
| `/buyers` | ক্রেতাদের তালিকা |
| `/addbuyer নাম` | ক্রেতার ইনভাইট লিংক |
| `/removebuyer ID` | ক্রেতা বাদ |
| `/deliver` | ডেলিভারি শুরু |
| `/stats` | পরিসংখ্যান |
| `/broadcast লেখা` | সবাইকে ঘোষণা (পাঠানোর আগে প্রিভিউ ও কনফার্ম) |
| `/help` | কমান্ড তালিকা |

**সাবমিটার যোগ করা:** `/approve তার_ID` দিন। অথবা সে নিজে বটে Start দিয়ে **Request Access** চাপলে আপনার কাছে Approve/Decline বোতাম আসবে।

**ক্রেতা যোগ করা:** `/addbuyer করিম` দিলে একটি লিংক পাবেন। লিংকটি করিমকে পাঠান। সে খুলে **Start** চাপলে তার যাচাইকৃত Chat ID নিজে থেকে সেভ হয়। লিংক একবারই কাজ করে।

**ডেলিভারি:** `Pending Files → ফাইল → Deliver to Buyer → ক্রেতা → Confirm Delivery`। ব্যর্থ হলে **Retry** বোতাম আসবে। আগে পাঠানো ফাইল আবার পাঠাতে গেলে ⚠️ সতর্কতা আসবে।

**ব্যাকআপ:** প্রতিদিন নিজে থেকে `DATA_DIR/backups`-এ হয় (`BACKUP_KEEP` সংখ্যক রাখে)। `Bot Settings → Backup Database Now` চাপলে ব্যাকআপ আপনার Telegram-এ চলে আসে। একই সার্ভারে থাকা ব্যাকআপ সার্ভার হারালে হারায়, তাই মাঝে মাঝে এই বোতামে ফোনে সংরক্ষণ করুন।

## ৯. ঐচ্ছিক: প্রাইভেট Google Sheet

Public (Anyone with link → Viewer) শিট কনফিগ ছাড়াই কাজ করে। প্রাইভেট শিটের জন্য:

1. `console.cloud.google.com` → নতুন প্রজেক্ট।
2. **APIs & Services → Library** → **Google Drive API** → **Enable**।
3. **IAM & Admin → Service Accounts → Create** → একটি নাম দিন।
4. সার্ভিস অ্যাকাউন্ট খুলে **Keys → Add key → Create new key → JSON**। ফাইল নামবে।
5. JSON ফাইলের লেখা কপি করে সার্ভারে:
```bash
mkdir -p ~/secrets && nano ~/secrets/service_account.json
chmod 600 ~/secrets/service_account.json
```
6. `.env`-এ `GOOGLE_SERVICE_ACCOUNT_FILE=/home/ubuntu/secrets/service_account.json` বসিয়ে `sudo systemctl restart filebot`।
7. জমাদাতাকে বলুন শিটটি সার্ভিস অ্যাকাউন্টের ইমেইলে (JSON-এর `client_email`) **Viewer** হিসেবে শেয়ার করতে। প্রাইভেট শিটের লিংক দিলে বট নিজেই ইমেইলটি জানিয়ে দেবে।

Google কনসোলের মেনুর নাম বদলাতে পারে। সাধারণত এতে বিলিং চালু লাগে না। বিলিং চালু করতে বললে এই ঐচ্ছিক ফিচারটি বাদ দিন।

## ১০. টেস্ট চালানো (ঐচ্ছিক)

টেস্ট চালানো বাধ্যতামূলক নয়, বট টেস্ট ছাড়াই চলে। চালাতে চাইলে:
```bash
cd ~/telegram_file_bot
source venv/bin/activate
pytest -q
```
টেস্টগুলো অ্যাডমিন/সাবমিটার অনুমোদন, ফাইল ভ্যালিডেশন, ক্রেতা নিবন্ধন, ফাইল জমা, ডেলিভারি, ডাটাবেস স্থায়িত্ব ও ডুপ্লিকেট ডেলিভারি আটকানো যাচাই করে। এগুলো কোনো আসল Telegram সংযোগ ব্যবহার করে না।

## ১১. সমস্যা সমাধান

| সমস্যা | সমাধান |
|---|---|
| `BOT_TOKEN সেট করা নেই` | `.env` ফাইল প্রজেক্ট ফোল্ডারে আছে কি না দেখুন (`ls -a`)। নাম ঠিক `.env` হতে হবে |
| `ADMIN_ID অবশ্যই সংখ্যা` | `=` এর পরে স্পেস, অক্ষর বা উদ্ধৃতিচিহ্ন আছে কি না দেখুন |
| `InvalidToken` / Unauthorized | টোকেন ভুল বা revoke হয়েছে। BotFather থেকে আবার নিন |
| বট উত্তর দেয় না | `sudo systemctl status filebot` ও `sudo journalctl -u filebot -n 50` দেখুন |
| `Conflict` ত্রুটি | একই টোকেনে দুই জায়গায় বট চলছে। Termux বন্ধ করুন, শুধু সার্ভারে চালান |
| আপনার কাছে বার্তা আসে না | নিজের বটে `/start` দিয়েছেন কি না দেখুন |
| ক্রেতাকে ডেলিভারি ব্যর্থ ("blocked or not started") | ক্রেতাকে বটে Start চাপাতে বলুন, প্রয়োজনে নতুন ইনভাইট লিংক দিন |
| "Network problem… NOT confirmed" | ক্রেতাকে জিজ্ঞেস করুন ফাইল এসেছে কি না, তারপর Retry করুন |
| ফাইল বাতিল: "login-secret field" | ফাইলে password, cookie, token, OTP, 2FA ইত্যাদি কলাম আছে। কলাম মুছে আবার পাঠাতে বলুন |
| "This is not a valid .xlsx" | ফাইলটি Excel-এ খুলে **Save As → .xlsx** করে পাঠাতে বলুন (.xls বা .csv নাম বদলালে চলে না) |
| ফাইল বড় | ২০ MB-র বেশি Telegram বটে নামানো যায় না |
| প্রাইভেট শিটে "No permission" | শিটটি সার্ভিস অ্যাকাউন্ট ইমেইলে Viewer হিসেবে শেয়ার করুন |
| "My Submissions" বোতামে ত্রুটি | `database.py`-তে `list_user_submissions` মেথডটি বসানো আছে কি না দেখুন |
| `pip install` ব্যর্থ | `sudo apt install -y python3-dev build-essential` চালিয়ে আবার চেষ্টা করুন |
| `bash deploy.sh` বলছে root দিয়ে চালাবেন না | `ubuntu` ইউজার দিয়ে ঢুকুন (`sudo` ছাড়া) |
| SSH-এ `Permission denied (publickey)` | `-i ~/.ssh/oracle_key` দিয়েছেন কি না এবং ইউজার নাম `ubuntu` কি না দেখুন |
| `Out of host capacity` | অন্য সময়ে বা অন্য Availability Domain-এ চেষ্টা করুন |
| সার্ভার বন্ধ (Stopped) | Oracle কনসোল → Instance → **Start**; তারপর বট নিজেই চালু হবে |

## ১২. নিরাপত্তা চেকলিস্ট

- [ ] `.env` GitHub-এ নেই (`git status`-এ দেখা যায় না)
- [ ] সার্ভারে `chmod 600 .env`
- [ ] টোকেন কোথাও পোস্ট করা হয়নি
- [ ] Oracle-এ Upgrade/PAYG চালু করা হয়নি
- [ ] নিয়মিত ব্যাকআপ ফোনে সংরক্ষণ করা হয়
