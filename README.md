# 🎰 Casino Bot — Setup Guide

## What you need (takes ~10 minutes)

- A Discord account
- A free [Railway.app](https://railway.app) account
- A free [GitHub.com](https://github.com) account

---

## Step 1 — Get Your Bot Token

1. Go to https://discord.com/developers/applications
2. Click **New Application** → give it any name → click **Create**
3. Click **Bot** in the left sidebar
4. Under **Privileged Gateway Intents**, turn ON:
   - ✅ SERVER MEMBERS INTENT
   - ✅ MESSAGE CONTENT INTENT
5. Click **Save Changes**
6. Click **Reset Token** → copy it (save it somewhere safe)

---

## Step 2 — Edit bot.py

Open `bot.py` and change line 12:

```python
OWNER_ID = 1335801328516993076   # ← replace with YOUR Discord user ID
```

**How to get your Discord User ID:**
Settings → Advanced → turn on **Developer Mode** → right-click your name anywhere → **Copy User ID**

Leave `BOT_TOKEN` as-is — you'll set it securely in Railway in Step 5.

---

## Step 3 — Invite the Bot to Your Server

1. In the Discord Developer Portal, go to **OAuth2 → URL Generator**
2. Under **SCOPES** check ✅ `bot`
3. Under **BOT PERMISSIONS** check:
   - ✅ Send Messages
   - ✅ Embed Links
   - ✅ Add Reactions
   - ✅ Read Message History
   - ✅ Manage Messages
4. Copy the URL at the bottom → open it in your browser → invite the bot

---

## Step 4 — Upload Files to GitHub

1. Go to https://github.com → click **New** (top left)
2. Name it anything (e.g. `casino-bot`) → click **Create repository**
3. Click **uploading an existing file**
4. Drag and drop all 4 files: `bot.py`, `requirements.txt`, `Procfile`, `data.json` (if you have one)
5. Click **Commit changes**

---

## Step 5 — Deploy 24/7 on Railway (Free)

1. Go to https://railway.app → sign up with GitHub
2. Click **New Project** → **Deploy from GitHub repo** → select your `casino-bot` repo
3. Railway will start deploying — wait for it to finish
4. Click your project → click the service → go to **Variables** tab
5. Click **New Variable** and add:
   - **Name:** `BOT_TOKEN`
   - **Value:** paste your token from Step 1
6. Railway will automatically restart the bot with the token

You should see `✅ YourBot#1234 is online!` in the Railway logs.

---

## All Commands (prefix: `!`)

| Command | Description |
|---------|-------------|
| `!help` | Show all commands |
| `!balance` | Check your balance |
| `!daily` | Free daily coins |
| `!weekly` | Free weekly coins |
| `!work` | Earn coins (1hr cooldown) |
| `!slots <bet>` | 🎰 Slot machine |
| `!coinflip <bet> <heads/tails>` | 🪙 Coin flip |
| `!dice <bet> <1-6>` | 🎲 Dice roll |
| `!blackjack <bet>` | 🃏 Blackjack |
| `!roulette <bet> <red/black/number>` | 🎡 Roulette |
| `!crash <bet>` | 📈 Crash game |
| `!mines <bet>` | 💣 Minesweeper |
| `!hilo <bet>` | 🔼 Hi-Lo |
| `!wheel <bet>` | 🎡 Prize wheel |
| `!race <bet> <1-5>` | 🐎 Horse race |
| `!trivia <bet>` | 🧠 Trivia |
| `!rob @user` | 🦹 Rob someone |
| `!transfer @user <amount>` | 💸 Send coins |
| `!leaderboard` | 🏆 Top 10 |
| `!profile` | 📊 Your stats |
| `!shop` / `!buy <item>` | 🛒 Shop |

> Tip: use `all` or `half` as your bet amount, e.g. `!slots all`

---

## Why `!` instead of `/`?

Discord's own slash command UI intercepts the `/` key before the bot sees it. Commands like `!balance` work 100% reliably. If you really want `/`, you'd need to register slash commands through Discord's API (a much bigger rewrite).

---

## Tips

- Data is saved in `data.json` — Railway resets this on redeploys. Back it up if needed.
- To reset someone's data: `!resetuser @user`
- To give coins: `!addcoins @user 1000`
