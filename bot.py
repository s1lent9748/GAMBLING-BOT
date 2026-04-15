import discord
from discord.ext import commands
import json
import random
import asyncio
import os
import time
import threading
from datetime import datetime, timedelta
from collections import defaultdict
from http.server import HTTPServer, BaseHTTPRequestHandler

# ============================================================
#  CONFIG — edit these, or set BOT_TOKEN as an env variable
# ============================================================
BOT_TOKEN     = os.getenv("BOT_TOKEN", "MTQ5MzcyMjA1MTQ0MDI4Mzc0OQ.GWgGyk.ANpAjXKYckT2E2c8wTGyaFXosEWX53bi1uI14c")
OWNER_ID      = 1335801328516993076      # your Discord user ID (integer)
PREFIX        = "!"
CURRENCY      = "🪙"
CURRENCY_NAME = "coins"
MINIMUM_CREATE_COST = 100_000           # 100,000 coins triggers a private ticket channel
# ============================================================

# ──────────────────────────────────────────────────────────────
# Keep-alive web server
# ──────────────────────────────────────────────────────────────

class _SilentHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")
    def log_message(self, *args):
        pass

def keep_alive():
    port = int(os.getenv("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), _SilentHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    print(f"✅ Keep-alive server running on port {port}")

# ──────────────────────────────────────────────────────────────
# Bot setup
# ──────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

DATA_FILE = "data.json"

# ──────────────────────────────────────────────────────────────
# Data helpers
# ──────────────────────────────────────────────────────────────

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"users": {}, "requests": [], "shop": {}}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_user(data, user_id: str):
    uid = str(user_id)
    if uid not in data["users"]:
        data["users"][uid] = {
            "balance": 500,
            "total_won": 0,
            "total_lost": 0,
            "games_played": 0,
            "daily_last": None,
            "weekly_last": None,
            "inventory": [],
            "level": 1,
            "xp": 0,
        }
    return data["users"][uid]

def add_xp(user, amount):
    user["xp"] += amount
    while user["xp"] >= user["level"] * 100:
        user["xp"] -= user["level"] * 100
        user["level"] += 1

def make_embed(title, description, color=0xFFD700):
    return discord.Embed(title=title, description=description, color=color)

# ──────────────────────────────────────────────────────────────
# Bot events
# ──────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    print(f"✅  {bot.user} is online! Prefix: {PREFIX}")
    await bot.change_presence(activity=discord.Game(name=f"{PREFIX}help | Casino 🎰"))

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(embed=make_embed("❌ Missing Argument",
            f"Use `{PREFIX}help` to see how to use this command.", 0xFF4444))
    elif isinstance(error, commands.BadArgument):
        await ctx.send(embed=make_embed("❌ Bad Argument",
            "Please provide a valid value.", 0xFF4444))
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(embed=make_embed("⏳ Cooldown",
            f"Wait **{error.retry_after:.1f}s** before using this again.", 0xFF8800))
    elif isinstance(error, commands.CheckFailure):
        pass  # silently ignore non-owner on owner-only commands
    elif isinstance(error, commands.CommandNotFound):
        pass

# ──────────────────────────────────────────────────────────────
# HELP COMMAND
# ──────────────────────────────────────────────────────────────

@bot.command(name="help")
async def help_cmd(ctx, category: str = None):
    P = PREFIX
    is_owner = ctx.author.id == OWNER_ID

    categories = {
        "economy": {
            "emoji": "💰",
            "owner_only": False,
            "commands": [
                (f"{P}balance [@user]",         "Check your or someone's balance"),
                (f"{P}daily",                   "Claim your daily reward (24hr)"),
                (f"{P}weekly",                  "Claim your weekly reward (7 days)"),
                (f"{P}work",                    "Work for coins (1hr cooldown)"),
                (f"{P}transfer @user <amount>", "Send coins to another user"),
                (f"{P}leaderboard",             "Top 10 richest players"),
                (f"{P}profile [@user]",         "View full stats profile"),
                (f"{P}shop",                    "Browse the item shop"),
                (f"{P}buy <item>",              "Buy an item from the shop"),
                (f"{P}inventory [@user]",       "View your inventory"),
            ]
        },
        "games": {
            "emoji": "🎮",
            "owner_only": False,
            "commands": [
                (f"{P}slots <bet>",                    "🎰 Slot machine — up to 50x (rare!)"),
                (f"{P}coinflip <bet> <h/t>",           "🪙 Coin flip — 2x"),
                (f"{P}dice <bet> <1-6>",               "🎲 Guess the dice — 4x"),
                (f"{P}blackjack <bet>",                "🃏 Full blackjack with hit/stand/double"),
                (f"{P}roulette <bet> <choice>",        "🎡 Roulette — red/black/number/etc"),
                (f"{P}crash <bet> [auto-cashout]",     "📈 Crash — cash out before it crashes"),
                (f"{P}mines <bet> [bombs 1-20]",       "💣 Minesweeper — choose your bomb count"),
                (f"{P}hilo <bet> [rounds 3-10]",       "🔼 Hi-Lo — choose how many rounds"),
                (f"{P}wheel <bet>",                    "🎡 Prize wheel — 9 segments"),
                (f"{P}race <bet> <1-5>",               "🐎 Horse racing — 1-in-5 chance"),
                (f"{P}trivia <bet>",                   "🧠 Trivia — answer to win"),
                (f"{P}rob @user",                      "🦹 Steal coins — 15% success rate"),
            ]
        },
        "request": {
            "emoji": "🌟",
            "owner_only": False,
            "commands": [
                (f"{P}usetocreate <amount> <request>", f"Spend {MINIMUM_CREATE_COST:,} coins to request a custom game from the owner — opens a private ticket!"),
                (f"{P}myrequests",                     "View your submitted requests"),
            ]
        },
        "info": {
            "emoji": "📖",
            "owner_only": False,
            "commands": [
                (f"{P}help [category]",       "Show this help menu"),
                (f"{P}howtoplay <game>",       "Learn how to play any game in detail"),
            ]
        },
        "owner": {
            "emoji": "👑",
            "owner_only": True,
            "commands": [
                (f"{P}requests [pending/fulfilled]",   "View creation requests"),
                (f"{P}fulfill <id> [note]",            "Mark request done & notify user"),
                (f"{P}closeticket",                    "Close (delete) a ticket channel"),
                (f"{P}addcoins @user <amount>",        "Give coins to a user"),
                (f"{P}removecoins @user <amount>",     "Remove coins from a user"),
                (f"{P}setbalance @user <amount>",      "Set exact balance"),
                (f"{P}addshopitem <n> <price> <desc>", "Add item to shop"),
                (f"{P}removeshopitem <n>",             "Remove item from shop"),
                (f"{P}broadcast <message>",            "Server-wide announcement"),
                (f"{P}resetuser @user",                "Wipe a user's data"),
            ]
        }
    }

    # If a specific category is requested
    if category and category.lower() in categories:
        cat = categories[category.lower()]
        # Block non-owners from viewing owner category
        if cat["owner_only"] and not is_owner:
            await ctx.send(embed=make_embed("❌ Access Denied", "You don't have permission to view that.", 0xFF4444))
            return
        lines = "\n".join(f"`{cmd}` — {desc}" for cmd, desc in cat["commands"])
        await ctx.send(embed=make_embed(f"{cat['emoji']} {category.title()} Commands", lines))
        return

    # Overview — only show owner category to the owner
    desc = f"**Welcome to the Casino Bot!** 🎰\nUse `{P}help <category>` for details.\n\n"
    for name, cat in categories.items():
        if cat["owner_only"] and not is_owner:
            continue
        desc += f"{cat['emoji']} **{name.title()}** — `{P}help {name}`\n"
    desc += f"\n**Currency:** {CURRENCY} {CURRENCY_NAME.title()}\n**Starting balance:** 500 {CURRENCY_NAME}\n**Bet shortcuts:** `all` or `half`"
    desc += f"\n\n💡 Use `{P}howtoplay <game>` to learn how any game works!"
    await ctx.send(embed=make_embed("🎲 Casino Bot Help", desc))

# ──────────────────────────────────────────────────────────────
# HOW TO PLAY COMMAND
# ──────────────────────────────────────────────────────────────

GAME_GUIDES = {
    "slots": {
        "emoji": "🎰",
        "title": "How to Play: Slots",
        "guide": (
            "**Command:** `!slots <bet>`\n"
            "**Aliases:** `!slot`, `!s`\n\n"
            "**How it works:**\n"
            "Spin a 3×3 reel of symbols. The middle row is your result.\n\n"
            "**Winning:**\n"
            "• **3 matching symbols** in the middle row = JACKPOT 🎉\n"
            "• **2 matching symbols** in the middle row = small win (0.5x bet)\n"
            "• No match = you lose your bet\n\n"
            "**Symbol Multipliers (3-of-a-kind):**\n"
            "🍒 Cherry → 2x | 🍋 Lemon → 3x | 🍊 Orange → 4x\n"
            "🍇 Grapes → 6x | 🔔 Bell → 10x | 💎 Diamond → 20x | 7️⃣ Seven → 50x\n\n"
            "**Tips:**\n"
            "• Rare symbols (💎, 7️⃣) appear far less often — but pay massive!\n"
            "• Use `!slots half` to preserve your balance while playing.\n\n"
            "**Example:** `!slots 200` — bets 200 coins on the slots."
        )
    },
    "coinflip": {
        "emoji": "🪙",
        "title": "How to Play: Coin Flip",
        "guide": (
            "**Command:** `!coinflip <bet> <heads/tails>`\n"
            "**Aliases:** `!cf`, `!flip`\n\n"
            "**How it works:**\n"
            "Pick heads or tails and flip a coin. Simple 50/50 chance.\n\n"
            "**Winning:**\n"
            "• Correct guess → **+bet** (2x total payout)\n"
            "• Wrong guess → **-bet**\n\n"
            "**Tips:**\n"
            "• You can use `h` or `t` as shortcuts.\n"
            "• Pure 50/50 — no strategy, just luck!\n\n"
            "**Example:** `!coinflip 500 heads` — bets 500 on heads."
        )
    },
    "dice": {
        "emoji": "🎲",
        "title": "How to Play: Dice Roll",
        "guide": (
            "**Command:** `!dice <bet> <1-6>`\n"
            "**Aliases:** `!roll`, `!d`\n\n"
            "**How it works:**\n"
            "Guess which number (1–6) the dice will land on.\n\n"
            "**Winning:**\n"
            "• Correct guess → **+bet × 4** (4x payout)\n"
            "• Wrong guess → **-bet**\n\n"
            "**Tips:**\n"
            "• 1-in-6 chance to win, but pays 4x — the house has a small edge.\n"
            "• Great for big wins if you're feeling lucky!\n\n"
            "**Example:** `!dice 300 4` — bets 300 coins and guesses the dice shows 4."
        )
    },
    "blackjack": {
        "emoji": "🃏",
        "title": "How to Play: Blackjack",
        "guide": (
            "**Command:** `!blackjack <bet>`\n"
            "**Aliases:** `!bj`\n\n"
            "**Objective:** Get closer to 21 than the dealer without going over.\n\n"
            "**Card Values:**\n"
            "• 2–10 = face value | J, Q, K = 10 | Ace = 11 (or 1 if needed)\n\n"
            "**Actions (react with the emoji):**\n"
            "• ✅ **Hit** — draw another card\n"
            "• 🛑 **Stand** — keep your hand, let the dealer play\n"
            "• ⬆️ **Double Down** — double your bet and draw exactly 1 more card\n\n"
            "**Outcomes:**\n"
            "• Beat dealer (closer to 21) → **+bet**\n"
            "• Natural Blackjack (21 on first 2 cards) → **+1.5× bet** 🎉\n"
            "• Bust (go over 21) → **-bet**\n"
            "• Tie → bet returned\n\n"
            "**Dealer rules:** Dealer always hits until reaching 17+.\n\n"
            "**Example:** `!blackjack 1000` — bets 1,000 coins."
        )
    },
    "roulette": {
        "emoji": "🎡",
        "title": "How to Play: Roulette",
        "guide": (
            "**Command:** `!roulette <bet> <choice>`\n"
            "**Aliases:** `!rou`\n\n"
            "**How it works:** The ball lands on a number 0–36. Bet on where it lands.\n\n"
            "**Bet Types & Payouts:**\n"
            "• `red` / `black` → 2x (even money bet)\n"
            "• `odd` / `even` → 2x\n"
            "• `low` (1–18) / `high` (19–36) → 2x\n"
            "• `1st12` (1–12) / `2nd12` (13–24) / `3rd12` (25–36) → 3x\n"
            "• `green` / `0` → 36x (rare!)\n"
            "• A specific **number** (0–36) → 36x\n\n"
            "**Tips:**\n"
            "• Red/Black is safest — near 50/50 chance.\n"
            "• Betting a specific number is risky but pays 36x!\n\n"
            "**Example:** `!roulette 500 red` — bets 500 on red.\n"
            "`!roulette 100 17` — bets 100 on the number 17."
        )
    },
    "crash": {
        "emoji": "📈",
        "title": "How to Play: Crash",
        "guide": (
            "**Command:** `!crash <bet> [auto-cashout]`\n\n"
            "**How it works:**\n"
            "A multiplier starts at 1x and rises. It will **crash** at a random point.\n"
            "Cash out before it crashes to win your bet × current multiplier.\n\n"
            "**Actions:**\n"
            "• React 🛑 to **manually cash out** at the current multiplier\n"
            "• Or set **auto-cashout**: `!crash 500 2.5` — automatically cashes out at 2.5x\n\n"
            "**Outcomes:**\n"
            "• Cash out in time → profit = **bet × multiplier**\n"
            "• Crash before you cash out → **-bet**\n\n"
            "**Tips:**\n"
            "• The multiplier crashes early most of the time — don't get greedy!\n"
            "• Use auto-cashout to lock in a safe target without reaction time stress.\n\n"
            "**Example:** `!crash 200` — bets 200, cash out manually.\n"
            "`!crash 200 1.5` — auto-cashes out at 1.5x if it gets there."
        )
    },
    "mines": {
        "emoji": "💣",
        "title": "How to Play: Mines",
        "guide": (
            "**Command:** `!mines <bet> [bombs]`\n\n"
            "**How it works:**\n"
            "A 5×5 grid (25 tiles) hides bombs and diamonds. Reveal tiles to earn more.\n\n"
            "**Customization:**\n"
            "• Choose **1–20 bombs** (default: 5). More bombs = higher multiplier per tile!\n\n"
            "**Actions (type in chat):**\n"
            "• Type a number **1–25** to reveal that tile\n"
            "• Type `cashout` to take your current winnings\n\n"
            "**Outcomes:**\n"
            "• Reveal a 💎 diamond → multiplier grows, keep going or cash out\n"
            "• Reveal a 💣 bomb → **-bet**, game over\n"
            "• Reveal all safe tiles → massive win!\n\n"
            "**Tips:**\n"
            "• High bombs (15–20) = ultra risky but insane multipliers\n"
            "• Low bombs (1–3) = safer, but smaller multipliers\n"
            "• Cash out early and often — greed kills!\n\n"
            "**Example:** `!mines 500 10` — bets 500 with 10 bombs on the grid."
        )
    },
    "hilo": {
        "emoji": "🔼",
        "title": "How to Play: Hi-Lo",
        "guide": (
            "**Command:** `!hilo <bet> [rounds]`\n\n"
            "**How it works:**\n"
            "A card is shown. Guess if the next card is **higher** or **lower**.\n"
            "Each correct guess multiplies your winnings by 1.8x!\n\n"
            "**Customization:**\n"
            "• Choose **3–10 rounds** (default: 5). More rounds = bigger potential win!\n\n"
            "**Actions (react):**\n"
            "• 🔼 **Higher** — next card is higher\n"
            "• 🔽 **Lower** — next card is lower\n"
            "• 🛑 **Cash Out** — take your current winnings and quit\n\n"
            "**Card Order (low → high):**\n"
            "2, 3, 4, 5, 6, 7, 8, 9, 10, J, Q, K, A\n\n"
            "**Tips:**\n"
            "• Ties (same card) replay the round.\n"
            "• Cash out after 2–3 correct guesses — it compounds fast!\n\n"
            "**Example:** `!hilo 300` — bets 300 for 5 rounds.\n"
            "`!hilo 300 8` — bets 300 for 8 rounds."
        )
    },
    "wheel": {
        "emoji": "🎡",
        "title": "How to Play: Wheel",
        "guide": (
            "**Command:** `!wheel <bet>`\n"
            "**Aliases:** `!spin`\n\n"
            "**How it works:**\n"
            "Spin the prize wheel and land on one of 9 segments.\n\n"
            "**Segments (weighted probabilities):**\n"
            "💀 Bankrupt — lose everything! (25%)\n"
            "0.2x — lose 80% of bet (20%)\n"
            "0.5x — lose 50% of bet (18%)\n"
            "1x — bet refunded, break even (12%)\n"
            "1.5x — win half your bet (10%)\n"
            "2x — double your bet (7%)\n"
            "3x — triple (5%)\n"
            "5x — 5× your bet (2%)\n"
            "10x 🌟 — jackpot! (1%)\n\n"
            "**Tips:**\n"
            "• The wheel is volatile — bankrupt is the most common outcome!\n"
            "• Don't spin your whole balance — risk only what you can lose.\n\n"
            "**Example:** `!wheel 100` — bets 100 coins."
        )
    },
    "race": {
        "emoji": "🐎",
        "title": "How to Play: Horse Race",
        "guide": (
            "**Command:** `!race <bet> <1-5>`\n\n"
            "**How it works:**\n"
            "5 horses race across a track. Pick your horse and cheer it on!\n\n"
            "**Horses:**\n"
            "1. 🐎 Thunder | 2. 🐎 Lightning | 3. 🐎 Storm | 4. 🐎 Blaze | 5. 🐎 Shadow\n\n"
            "**Winning:**\n"
            "• Your horse wins → **+bet × 4** 🎉\n"
            "• Your horse loses → **-bet**\n\n"
            "**Tips:**\n"
            "• All horses have equal odds — purely luck!\n"
            "• 1-in-5 chance, 4x payout — the house has a slight edge.\n\n"
            "**Example:** `!race 200 3` — bets 200 coins on horse #3 (Storm)."
        )
    },
    "trivia": {
        "emoji": "🧠",
        "title": "How to Play: Trivia",
        "guide": (
            "**Command:** `!trivia <bet>`\n\n"
            "**How it works:**\n"
            "Answer a random trivia question correctly to double your bet!\n\n"
            "**Rules:**\n"
            "• You have **15 seconds** to type your answer in chat\n"
            "• Answer must match exactly (case-insensitive)\n"
            "• No partial credit — must be the exact answer\n\n"
            "**Winning:**\n"
            "• Correct → **+bet** (2x total)\n"
            "• Wrong or timeout → **-bet**\n\n"
            "**Tips:**\n"
            "• Don't overthink it — answers are straightforward\n"
            "• Trivia has a 30 second cooldown between uses\n\n"
            "**Example:** `!trivia 500` — bets 500 coins on trivia."
        )
    },
    "rob": {
        "emoji": "🦹",
        "title": "How to Play: Rob",
        "guide": (
            "**Command:** `!rob @user`\n"
            "**Aliases:** `!steal`\n\n"
            "**How it works:**\n"
            "Attempt to steal coins from another player.\n\n"
            "**Outcomes:**\n"
            "• **15% chance** of success → steal a random amount (up to 25% of their balance)\n"
            "• **85% chance** of getting caught → pay a fine to the victim\n\n"
            "**Requirements:**\n"
            "• Target must have at least 100 coins\n"
            "• 5 minute cooldown between rob attempts\n\n"
            "**Tips:**\n"
            "• Robbing is very risky — you'll likely lose money!\n"
            "• Only rob if you can afford the fine of 50–200 coins\n"
            "• There's no way to increase your success rate\n\n"
            "**Example:** `!rob @PlayerName` — attempt to rob that player."
        )
    },
    "blackjack2": None,  # alias handled below
}
# Allow both spellings
GAME_GUIDES["bj"] = GAME_GUIDES["blackjack"]
GAME_GUIDES["cf"] = GAME_GUIDES["coinflip"]
GAME_GUIDES["slot"] = GAME_GUIDES["slots"]
GAME_GUIDES["rou"] = GAME_GUIDES["roulette"]
GAME_GUIDES["steal"] = GAME_GUIDES["rob"]
GAME_GUIDES["spin"] = GAME_GUIDES["wheel"]
GAME_GUIDES["roll"] = GAME_GUIDES["dice"]

@bot.command(name="howtoplay", aliases=["htp", "tutorial", "guide"])
async def how_to_play(ctx, *, game: str = None):
    P = PREFIX
    game_list = (
        "`slots` `coinflip` `dice` `blackjack` `roulette` `crash` `mines` `hilo` `wheel` `race` `trivia` `rob`"
    )

    if not game:
        await ctx.send(embed=make_embed("📖 How To Play",
            f"**Usage:** `{P}howtoplay <game>`\n\n"
            f"**Available games:**\n{game_list}\n\n"
            f"**Example:** `{P}howtoplay mines`", 0x1E90FF))
        return

    key = game.lower().strip()
    if key not in GAME_GUIDES or GAME_GUIDES[key] is None:
        await ctx.send(embed=make_embed("❌ Unknown Game",
            f"No guide found for `{game}`.\n\n**Available games:**\n{game_list}", 0xFF4444))
        return

    g = GAME_GUIDES[key]
    await ctx.send(embed=make_embed(f"{g['emoji']} {g['title']}", g["guide"], 0x1E90FF))

# ──────────────────────────────────────────────────────────────
# ECONOMY COMMANDS
# ──────────────────────────────────────────────────────────────

@bot.command(name="balance", aliases=["bal", "money"])
async def balance(ctx, member: discord.Member = None):
    member = member or ctx.author
    data = load_data()
    u = get_user(data, member.id)
    save_data(data)
    e = make_embed(f"{member.display_name}'s Balance",
        f"{CURRENCY} **{u['balance']:,}** {CURRENCY_NAME}\n"
        f"📊 Level **{u['level']}** | XP **{u['xp']}** / {u['level']*100}\n"
        f"🏆 Won: {u['total_won']:,} | Lost: {u['total_lost']:,}")
    e.set_thumbnail(url=member.display_avatar.url)
    await ctx.send(embed=e)

@bot.command(name="daily")
@commands.cooldown(1, 5, commands.BucketType.user)
async def daily(ctx):
    data = load_data()
    u = get_user(data, ctx.author.id)
    now = datetime.utcnow()
    last = datetime.fromisoformat(u["daily_last"]) if u["daily_last"] else None
    if last and now - last < timedelta(days=1):
        remaining = timedelta(days=1) - (now - last)
        h = int(remaining.total_seconds()) // 3600
        m = (int(remaining.total_seconds()) % 3600) // 60
        await ctx.send(embed=make_embed("⏳ Daily Cooldown", f"Come back in **{h}h {m}m**.", 0xFF8800))
        return
    reward = 300 + (u["level"] - 1) * 30
    u["balance"] += reward
    u["daily_last"] = now.isoformat()
    add_xp(u, 20)
    save_data(data)
    await ctx.send(embed=make_embed("✅ Daily Reward!",
        f"You claimed **{reward:,}** {CURRENCY}!\nBalance: **{u['balance']:,}**"))

@bot.command(name="weekly")
@commands.cooldown(1, 5, commands.BucketType.user)
async def weekly(ctx):
    data = load_data()
    u = get_user(data, ctx.author.id)
    now = datetime.utcnow()
    last = datetime.fromisoformat(u["weekly_last"]) if u["weekly_last"] else None
    if last and now - last < timedelta(weeks=1):
        remaining = timedelta(weeks=1) - (now - last)
        d = int(remaining.total_seconds()) // 86400
        h = (int(remaining.total_seconds()) % 86400) // 3600
        await ctx.send(embed=make_embed("⏳ Weekly Cooldown", f"Come back in **{d}d {h}h**.", 0xFF8800))
        return
    reward = 1500 + (u["level"] - 1) * 150
    u["balance"] += reward
    u["weekly_last"] = now.isoformat()
    add_xp(u, 100)
    save_data(data)
    await ctx.send(embed=make_embed("✅ Weekly Reward!",
        f"You claimed **{reward:,}** {CURRENCY}!\nBalance: **{u['balance']:,}**"))

@bot.command(name="work")
@commands.cooldown(1, 3600, commands.BucketType.user)
async def work(ctx):
    data = load_data()
    u = get_user(data, ctx.author.id)
    jobs = [
        ("dealt cards at the casino",     60,  160),
        ("ran the roulette table",         80,  200),
        ("fixed slot machines",            50,  140),
        ("served drinks on the floor",     40,  110),
        ("counted chips",                  55,  130),
        ("secured the vault",             100,  220),
        ("managed the sports book",        75,  180),
    ]
    job, lo, hi = random.choice(jobs)
    earned = random.randint(lo, hi)
    u["balance"] += earned
    add_xp(u, 10)
    save_data(data)
    await ctx.send(embed=make_embed("💼 Work",
        f"You **{job}** and earned **{earned:,}** {CURRENCY}!\nBalance: **{u['balance']:,}**"))

@bot.command(name="transfer", aliases=["give", "pay"])
async def transfer(ctx, member: discord.Member, amount: int):
    if member.id == ctx.author.id:
        await ctx.send(embed=make_embed("❌ Error", "You can't transfer to yourself.", 0xFF4444)); return
    if amount <= 0:
        await ctx.send(embed=make_embed("❌ Error", "Amount must be positive.", 0xFF4444)); return
    data = load_data()
    sender = get_user(data, ctx.author.id)
    receiver = get_user(data, member.id)
    if sender["balance"] < amount:
        await ctx.send(embed=make_embed("❌ Insufficient Funds",
            f"You only have **{sender['balance']:,}** coins.", 0xFF4444)); return
    sender["balance"] -= amount
    receiver["balance"] += amount
    save_data(data)
    await ctx.send(embed=make_embed("💸 Transfer Complete",
        f"**{ctx.author.display_name}** → **{member.display_name}**\n"
        f"Amount: **{amount:,}** {CURRENCY}"))

@bot.command(name="leaderboard", aliases=["lb", "top"])
async def leaderboard(ctx):
    data = load_data()
    sorted_users = sorted(data["users"].items(), key=lambda x: x[1]["balance"], reverse=True)[:10]
    lines = []
    medals = ["🥇", "🥈", "🥉"]
    for i, (uid, u) in enumerate(sorted_users):
        try:
            member = ctx.guild.get_member(int(uid)) or await ctx.guild.fetch_member(int(uid))
            name = member.display_name
        except:
            name = f"User#{uid[-4:]}"
        prefix = medals[i] if i < 3 else f"**{i+1}.**"
        lines.append(f"{prefix} {name} — {CURRENCY} **{u['balance']:,}**")
    await ctx.send(embed=make_embed("🏆 Leaderboard", "\n".join(lines) or "No data yet."))

@bot.command(name="profile")
async def profile(ctx, member: discord.Member = None):
    member = member or ctx.author
    data = load_data()
    u = get_user(data, member.id)
    save_data(data)
    e = make_embed(f"🎲 {member.display_name}'s Profile", "")
    e.add_field(name="💰 Balance",      value=f"{CURRENCY} {u['balance']:,}", inline=True)
    e.add_field(name="📊 Level",        value=f"Lv. {u['level']} ({u['xp']}/{u['level']*100} XP)", inline=True)
    e.add_field(name="🎮 Games Played", value=str(u["games_played"]), inline=True)
    e.add_field(name="🏆 Total Won",    value=f"{u['total_won']:,}", inline=True)
    e.add_field(name="💸 Total Lost",   value=f"{u['total_lost']:,}", inline=True)
    net = u['total_won'] - u['total_lost']
    e.add_field(name="📈 Net",          value=f"{'+' if net >= 0 else ''}{net:,}", inline=True)
    e.set_thumbnail(url=member.display_avatar.url)
    await ctx.send(embed=e)

@bot.command(name="shop")
async def shop(ctx):
    data = load_data()
    if not data.get("shop"):
        await ctx.send(embed=make_embed("🛒 Shop",
            f"The shop is empty. Owner can add items with `{PREFIX}addshopitem`.")); return
    lines = [f"**{name}** — {CURRENCY} {info['price']:,}\n> {info['desc']}"
             for name, info in data["shop"].items()]
    await ctx.send(embed=make_embed("🛒 Item Shop", "\n\n".join(lines)))

@bot.command(name="buy")
async def buy(ctx, *, item: str):
    data = load_data()
    shop_data = data.get("shop", {})
    match = next((k for k in shop_data if k.lower() == item.lower()), None)
    if not match:
        await ctx.send(embed=make_embed("❌ Not Found",
            f"No item named **{item}** in the shop.", 0xFF4444)); return
    u = get_user(data, ctx.author.id)
    price = shop_data[match]["price"]
    if u["balance"] < price:
        await ctx.send(embed=make_embed("❌ Insufficient Funds",
            f"Need **{price:,}** coins. You have **{u['balance']:,}**.", 0xFF4444)); return
    u["balance"] -= price
    u["inventory"].append(match)
    save_data(data)
    await ctx.send(embed=make_embed("✅ Purchased!", f"You bought **{match}** for **{price:,}** {CURRENCY}!"))

@bot.command(name="inventory", aliases=["inv"])
async def inventory(ctx, member: discord.Member = None):
    member = member or ctx.author
    data = load_data()
    u = get_user(data, member.id)
    save_data(data)
    items = u.get("inventory", [])
    if not items:
        await ctx.send(embed=make_embed(f"🎒 {member.display_name}'s Inventory", "Empty inventory.")); return
    counts = defaultdict(int)
    for i in items:
        counts[i] += 1
    lines = [f"**{name}** x{qty}" for name, qty in counts.items()]
    await ctx.send(embed=make_embed(f"🎒 {member.display_name}'s Inventory", "\n".join(lines)))

# ──────────────────────────────────────────────────────────────
# GAMBLING HELPERS
# ──────────────────────────────────────────────────────────────

def parse_bet(u, amount_str):
    bal = u["balance"]
    if amount_str.lower() == "all":
        if bal <= 0:
            return None, "You have no coins to bet."
        return bal, None
    if amount_str.lower() == "half":
        if bal <= 0:
            return None, "You have no coins to bet."
        return max(1, bal // 2), None
    try:
        bet = int(amount_str)
    except ValueError:
        return None, "Bet must be a number, `all`, or `half`."
    if bet <= 0:
        return None, "Bet must be positive."
    if bet > bal:
        return None, f"You only have **{bal:,}** coins."
    return bet, None

async def send_result(ctx, user, won: bool, bet: int, payout: int, title: str, detail: str):
    user["games_played"] += 1
    if won:
        user["balance"] += payout
        user["total_won"] += payout
        add_xp(user, max(1, payout // 50))
        color = 0x00FF88
        result = f"**+{payout:,}** {CURRENCY} — you win! 🎉"
    else:
        user["balance"] -= bet
        user["total_lost"] += bet
        color = 0xFF4444
        result = f"**-{bet:,}** {CURRENCY} — better luck next time."
    e = make_embed(title, f"{detail}\n\n{result}\n💰 Balance: **{user['balance']:,}**", color)
    await ctx.send(embed=e)

# ──────────────────────────────────────────────────────────────
# GAMBLING GAMES
# ──────────────────────────────────────────────────────────────

# ── SLOTS ──────────────────────────────────────────────────────
# Weighted selection makes rare/high-payout symbols appear less often
SLOT_SYMBOLS  = ["🍒", "🍋", "🍊", "🍇", "🔔", "💎", "7️⃣"]
SLOT_WEIGHTS  = [30,   25,   20,   12,    8,    4,    1  ]   # 7s are very rare
SLOT_MULTS    = {"🍒": 2, "🍋": 3, "🍊": 4, "🍇": 6, "🔔": 10, "💎": 20, "7️⃣": 50}

@bot.command(name="slots", aliases=["slot", "s"])
async def slots(ctx, amount: str):
    data = load_data()
    u = get_user(data, ctx.author.id)
    bet, err = parse_bet(u, amount)
    if err:
        await ctx.send(embed=make_embed("❌ Error", err, 0xFF4444)); return

    reels = [[random.choices(SLOT_SYMBOLS, weights=SLOT_WEIGHTS, k=1)[0] for _ in range(3)] for _ in range(3)]
    middle = reels[1]
    display = "\n".join("│ " + " │ ".join(row) + " │" for row in reels)
    display = f"╔═══════════════╗\n{display}\n╚═══════════════╝"

    if middle[0] == middle[1] == middle[2]:
        sym = middle[0]
        mult = SLOT_MULTS[sym]
        payout = int(bet * mult)
        await send_result(ctx, u, True, bet, payout, "🎰 Slots — JACKPOT! 🎉",
            f"{display}\n\n**3x {sym}** — {mult}x multiplier!")
    elif middle[0] == middle[1] or middle[1] == middle[2]:
        payout = int(bet * 0.25)  # small consolation — 0.25x back (reduced from 0.5x)
        await send_result(ctx, u, True, bet, payout, "🎰 Slots — Small Win",
            f"{display}\n\nTwo in a row — 0.25x back!")
    else:
        await send_result(ctx, u, False, bet, 0, "🎰 Slots — Miss!", display)
    save_data(data)

# ── COINFLIP ───────────────────────────────────────────────────
@bot.command(name="coinflip", aliases=["cf", "flip"])
async def coinflip(ctx, amount: str, side: str = "heads"):
    data = load_data()
    u = get_user(data, ctx.author.id)
    bet, err = parse_bet(u, amount)
    if err:
        await ctx.send(embed=make_embed("❌ Error", err, 0xFF4444)); return
    side = side.lower()
    if side not in ("heads", "tails", "h", "t"):
        await ctx.send(embed=make_embed("❌ Error", "Choose `heads` or `tails`.", 0xFF4444)); return
    choice = "heads" if side in ("heads", "h") else "tails"
    result = random.choice(["heads", "tails"])
    coin = "🪙" if result == "heads" else "🔘"
    detail = f"You chose **{choice}**, it landed **{result}** {coin}"
    await send_result(ctx, u, choice == result, bet, bet, "🪙 Coin Flip", detail)
    save_data(data)

# ── DICE ───────────────────────────────────────────────────────
@bot.command(name="dice", aliases=["roll", "d"])
async def dice(ctx, amount: str, guess: int):
    data = load_data()
    u = get_user(data, ctx.author.id)
    bet, err = parse_bet(u, amount)
    if err:
        await ctx.send(embed=make_embed("❌ Error", err, 0xFF4444)); return
    if not 1 <= guess <= 6:
        await ctx.send(embed=make_embed("❌ Error", "Guess must be 1–6.", 0xFF4444)); return
    roll = random.randint(1, 6)
    dice_faces = ["⚀","⚁","⚂","⚃","⚄","⚅"]
    detail = f"You guessed **{guess}**, rolled **{dice_faces[roll-1]} ({roll})**"
    await send_result(ctx, u, roll == guess, bet, bet * 4, "🎲 Dice Roll", detail)  # 4x (down from 5x)
    save_data(data)

# ── BLACKJACK ─────────────────────────────────────────────────
def draw_card():
    suits  = ["♠","♥","♦","♣"]
    ranks  = ["2","3","4","5","6","7","8","9","10","J","Q","K","A"]
    return random.choice(ranks), random.choice(suits)

def card_value(rank):
    if rank in ("J","Q","K"): return 10
    if rank == "A": return 11
    return int(rank)

def hand_value(hand):
    val = sum(card_value(r) for r, _ in hand)
    aces = sum(1 for r, _ in hand if r == "A")
    while val > 21 and aces:
        val -= 10; aces -= 1
    return val

def fmt_hand(hand):
    return " ".join(f"[{r}{s}]" for r, s in hand)

@bot.command(name="blackjack", aliases=["bj"])
async def blackjack(ctx, amount: str):
    data = load_data()
    u = get_user(data, ctx.author.id)
    bet, err = parse_bet(u, amount)
    if err:
        await ctx.send(embed=make_embed("❌ Error", err, 0xFF4444)); return

    player = [draw_card(), draw_card()]
    dealer = [draw_card(), draw_card()]

    def status_embed(show_dealer=False, extra=""):
        dh = fmt_hand(dealer) if show_dealer else f"[{dealer[0][0]}{dealer[0][1]}] [?]"
        pv = hand_value(player)
        dv = hand_value(dealer) if show_dealer else "?"
        desc = (f"**Dealer:** {dh} ({dv})\n"
                f"**You:**    {fmt_hand(player)} ({pv})\n\n"
                f"Bet: **{bet:,}** {CURRENCY}\n{extra}\n\n"
                f"React ✅ Hit  |  🛑 Stand  |  ⬆️ Double Down")
        return make_embed("🃏 Blackjack", desc, 0x1E90FF)

    if hand_value(player) == 21:
        payout = int(bet * 1.5)
        u["balance"] += payout; u["total_won"] += payout; u["games_played"] += 1
        add_xp(u, payout // 50); save_data(data)
        await ctx.send(embed=make_embed("🃏 Blackjack — BLACKJACK!",
            f"**{fmt_hand(player)}** — Natural 21!\n**+{payout:,}** {CURRENCY} 🎉\n"
            f"Balance: **{u['balance']:,}**", 0xFFD700))
        return

    msg = await ctx.send(embed=status_embed())
    for emoji in ["✅", "🛑", "⬆️"]:
        await msg.add_reaction(emoji)

    doubled = False
    while True:
        def check(reaction, user):
            return (user == ctx.author and str(reaction.emoji) in ["✅","🛑","⬆️"]
                    and reaction.message.id == msg.id)
        try:
            reaction, _ = await bot.wait_for("reaction_add", timeout=30.0, check=check)
        except asyncio.TimeoutError:
            await msg.edit(embed=make_embed("🃏 Blackjack — Timeout", "Game cancelled.", 0x888888)); return

        action = str(reaction.emoji)
        if action == "✅":
            player.append(draw_card())
            if hand_value(player) > 21:
                break
            await msg.edit(embed=status_embed())
            try:
                await msg.remove_reaction(action, ctx.author)
            except:
                pass
        elif action == "🛑":
            break
        elif action == "⬆️" and not doubled:
            if u["balance"] >= bet:
                bet *= 2
                doubled = True
                player.append(draw_card())
                break
            else:
                await ctx.send(embed=make_embed("❌ Error", "Not enough coins to double down.", 0xFF4444))

    while hand_value(dealer) < 17:
        dealer.append(draw_card())

    pv = hand_value(player)
    dv = hand_value(dealer)
    u["games_played"] += 1

    if pv > 21:
        u["balance"] -= bet; u["total_lost"] += bet
        result = f"❌ Bust! ({pv}) — **-{bet:,}** {CURRENCY}"
        color = 0xFF4444
    elif dv > 21 or pv > dv:
        u["balance"] += bet; u["total_won"] += bet
        add_xp(u, bet // 50)
        result = f"✅ You win! ({pv} vs {dv}) — **+{bet:,}** {CURRENCY} 🎉"
        color = 0x00FF88
    elif pv == dv:
        result = f"🤝 Push! ({pv}) — Bet returned."
        color = 0xFFD700
    else:
        u["balance"] -= bet; u["total_lost"] += bet
        result = f"❌ Dealer wins. ({pv} vs {dv}) — **-{bet:,}** {CURRENCY}"
        color = 0xFF4444

    save_data(data)
    final = (f"**Dealer:** {fmt_hand(dealer)} ({dv})\n"
             f"**You:** {fmt_hand(player)} ({pv})\n\n{result}\n\n"
             f"Balance: **{u['balance']:,}** {CURRENCY}")
    await msg.edit(embed=make_embed("🃏 Blackjack — Result", final, color))

# ── ROULETTE ──────────────────────────────────────────────────
ROULETTE_REDS = {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}

@bot.command(name="roulette", aliases=["rou"])
async def roulette(ctx, amount: str, *, choice: str):
    data = load_data()
    u = get_user(data, ctx.author.id)
    bet, err = parse_bet(u, amount)
    if err:
        await ctx.send(embed=make_embed("❌ Error", err, 0xFF4444)); return

    spin = random.randint(0, 36)
    spin_color = "🟢" if spin == 0 else ("🔴" if spin in ROULETTE_REDS else "⬛")
    choice = choice.lower().strip()

    won = False; mult = 1
    if choice.isdigit():
        won = int(choice) == spin; mult = 35
    elif choice in ("red", "r"):
        won = spin in ROULETTE_REDS
    elif choice in ("black", "b"):
        won = spin not in ROULETTE_REDS and spin != 0
    elif choice in ("green", "g", "0"):
        won = spin == 0; mult = 35
    elif choice in ("even", "e"):
        won = spin != 0 and spin % 2 == 0
    elif choice in ("odd", "o"):
        won = spin % 2 == 1
    elif choice in ("1-18", "low"):
        won = 1 <= spin <= 18
    elif choice in ("19-36", "high"):
        won = 19 <= spin <= 36
    elif choice in ("1st12", "1-12"):
        won = 1 <= spin <= 12; mult = 2
    elif choice in ("2nd12", "13-24"):
        won = 13 <= spin <= 24; mult = 2
    elif choice in ("3rd12", "25-36"):
        won = 25 <= spin <= 36; mult = 2
    else:
        await ctx.send(embed=make_embed("❌ Invalid Choice",
            "Options: `red` `black` `green` `odd` `even` `low` `high` `1st12` `2nd12` `3rd12` or a number 0–36.",
            0xFF4444)); return

    detail = f"Ball landed on **{spin_color} {spin}**\nYour bet: **{choice}**"
    await send_result(ctx, u, won, bet, bet * mult, "🎡 Roulette", detail)
    save_data(data)

# ── CRASH ─────────────────────────────────────────────────────
@bot.command(name="crash")
async def crash(ctx, amount: str, auto_cashout: float = 0.0):
    data = load_data()
    u = get_user(data, ctx.author.id)
    bet, err = parse_bet(u, amount)
    if err:
        await ctx.send(embed=make_embed("❌ Error", err, 0xFF4444)); return

    if auto_cashout != 0.0 and auto_cashout <= 1.0:
        await ctx.send(embed=make_embed("❌ Error", "Auto-cashout must be greater than 1.0 (e.g. `1.5` or `3.0`).", 0xFF4444)); return

    # Weighted crash point: crashes early most of the time
    r = random.random()
    if r < 0.55:
        crash_point = round(random.uniform(1.0, 1.8), 2)   # 55% crash very early
    elif r < 0.80:
        crash_point = round(random.uniform(1.8, 4.0), 2)   # 25% moderate
    elif r < 0.95:
        crash_point = round(random.uniform(4.0, 10.0), 2)  # 15% decent
    else:
        crash_point = round(random.uniform(10.0, 20.0), 2) # 5% high multiplier

    current = 1.00
    auto_str = f" | Auto-cashout: **{auto_cashout:.2f}x**" if auto_cashout > 1.0 else ""
    msg = await ctx.send(embed=make_embed("📈 Crash",
        f"Multiplier: **{current:.2f}x** 🚀\nBet: **{bet:,}**{auto_str}\n\nReact 🛑 to cash out!", 0x1E90FF))
    await msg.add_reaction("🛑")

    cashed_out = False
    cashout_mult = 1.0

    async def ticker():
        nonlocal current, cashed_out, cashout_mult
        step = 0.1
        while current < crash_point:
            await asyncio.sleep(1.5)
            current = round(current + step, 2)
            step = round(step * 1.05, 3)
            # Auto-cashout check
            if auto_cashout > 1.0 and current >= auto_cashout and not cashed_out:
                cashed_out = True
                cashout_mult = current
                return
            if cashed_out:
                return
            try:
                await msg.edit(embed=make_embed("📈 Crash",
                    f"Multiplier: **{current:.2f}x** 🚀\nBet: **{bet:,}**{auto_str}\n\nReact 🛑 to cash out!", 0x00FF88))
            except:
                return

    tick_task = asyncio.create_task(ticker())

    def check(reaction, user):
        return user == ctx.author and str(reaction.emoji) == "🛑" and reaction.message.id == msg.id

    try:
        await bot.wait_for("reaction_add", timeout=30.0, check=check)
        if not cashed_out:
            cashed_out = True
            cashout_mult = current
    except asyncio.TimeoutError:
        pass

    tick_task.cancel()
    u["games_played"] += 1

    if cashed_out and cashout_mult <= crash_point:
        payout = int(bet * cashout_mult) - bet
        u["balance"] += payout; u["total_won"] += payout
        add_xp(u, payout // 50); save_data(data)
        auto_note = " (auto)" if auto_cashout > 1.0 else ""
        await msg.edit(embed=make_embed("📈 Crash — Cashed Out! ✅",
            f"You cashed out at **{cashout_mult:.2f}x**{auto_note} (crashed at {crash_point:.2f}x)\n"
            f"**+{payout:,}** {CURRENCY} 🎉\nBalance: **{u['balance']:,}**", 0x00FF88))
    else:
        u["balance"] -= bet; u["total_lost"] += bet
        save_data(data)
        await msg.edit(embed=make_embed("📈 Crash — 💥 CRASHED!",
            f"Crashed at **{crash_point:.2f}x**\n**-{bet:,}** {CURRENCY}\n"
            f"Balance: **{u['balance']:,}**", 0xFF4444))

# ── HI-LO ─────────────────────────────────────────────────────
CARD_RANKS = ["2","3","4","5","6","7","8","9","10","J","Q","K","A"]

@bot.command(name="hilo")
async def hilo(ctx, amount: str, rounds: int = 5):
    if not 3 <= rounds <= 10:
        await ctx.send(embed=make_embed("❌ Error", "Rounds must be between 3 and 10.", 0xFF4444)); return

    data = load_data()
    u = get_user(data, ctx.author.id)
    bet, err = parse_bet(u, amount)
    if err:
        await ctx.send(embed=make_embed("❌ Error", err, 0xFF4444)); return

    current_rank = random.choice(CARD_RANKS)
    current_idx  = CARD_RANKS.index(current_rank)
    current_bet  = bet
    u["games_played"] += 1

    for round_num in range(1, rounds + 1):
        msg = await ctx.send(embed=make_embed("🔼 Hi-Lo",
            f"Round {round_num}/{rounds}\n\nCurrent card: **{current_rank}**\n"
            f"React 🔼 Higher  |  🔽 Lower  |  🛑 Cash Out\n\n"
            f"Current payout: **{int(current_bet):,}** {CURRENCY}"))
        for e in ["🔼", "🔽", "🛑"]:
            await msg.add_reaction(e)

        def check(r, usr):
            return usr == ctx.author and str(r.emoji) in ["🔼","🔽","🛑"] and r.message.id == msg.id
        try:
            reaction, _ = await bot.wait_for("reaction_add", timeout=20.0, check=check)
        except asyncio.TimeoutError:
            await msg.edit(embed=make_embed("🔼 Hi-Lo — Timeout", "Game cancelled.", 0x888888)); return

        action = str(reaction.emoji)
        if action == "🛑":
            profit = int(current_bet) - bet
            if profit > 0:
                u["balance"] += profit; u["total_won"] += profit
            save_data(data)
            await ctx.send(embed=make_embed("🔼 Hi-Lo — Cashed Out",
                f"Walked away with **{int(current_bet):,}** {CURRENCY}\nBalance: **{u['balance']:,}**", 0x00FF88))
            return

        next_rank = random.choice(CARD_RANKS)
        next_idx  = CARD_RANKS.index(next_rank)
        correct = (action == "🔼" and next_idx > current_idx) or (action == "🔽" and next_idx < current_idx)

        if next_idx == current_idx:
            await msg.edit(embed=make_embed("🔼 Hi-Lo — Same Card",
                f"It was **{next_rank}** — tie! Round replayed.", 0xFFD700))
        elif correct:
            current_bet *= 1.8
            current_rank = next_rank; current_idx = next_idx
            await msg.edit(embed=make_embed("🔼 Hi-Lo — Correct! ✅",
                f"It was **{next_rank}**! Payout now: **{int(current_bet):,}**", 0x00FF88))
        else:
            u["balance"] -= bet; u["total_lost"] += bet
            save_data(data)
            await msg.edit(embed=make_embed("🔼 Hi-Lo — Wrong ❌",
                f"It was **{next_rank}** — you lost **{bet:,}** {CURRENCY}\n"
                f"Balance: **{u['balance']:,}**", 0xFF4444))
            return
        await asyncio.sleep(1)

    profit = int(current_bet) - bet
    u["balance"] += profit; u["total_won"] += profit
    save_data(data)
    await ctx.send(embed=make_embed("🔼 Hi-Lo — Winner! 🎉",
        f"You went all {rounds} rounds!\n**+{profit:,}** {CURRENCY}\nBalance: **{u['balance']:,}**", 0xFFD700))

# ── WHEEL ─────────────────────────────────────────────────────
WHEEL_SEGMENTS = [
    ("💀 Bankrupt", 0.00),
    ("0.2x",        0.20),
    ("0.5x",        0.50),
    ("1x (refund)", 1.00),
    ("1.5x",        1.50),
    ("2x",          2.00),
    ("3x",          3.00),
    ("5x",          5.00),
    ("10x 🌟",      10.00),
]

@bot.command(name="wheel", aliases=["spin"])
async def wheel(ctx, amount: str):
    data = load_data()
    u = get_user(data, ctx.author.id)
    bet, err = parse_bet(u, amount)
    if err:
        await ctx.send(embed=make_embed("❌ Error", err, 0xFF4444)); return

    # Harder wheel — bankrupt and small wins more likely
    weights = [25, 20, 18, 12, 10, 7, 5, 2, 1]
    label, mult = random.choices(WHEEL_SEGMENTS, weights=weights, k=1)[0]
    u["games_played"] += 1

    if mult == 0:
        u["balance"] = 0; u["total_lost"] += bet
        save_data(data)
        await ctx.send(embed=make_embed("🎡 Prize Wheel",
            f"💀 **BANKRUPT!** The wheel landed on **{label}**\nBalance: **0**", 0xFF4444)); return

    payout = int(bet * mult) - bet
    if payout > 0:
        u["balance"] += payout; u["total_won"] += payout
        add_xp(u, payout // 50)
        result = f"**+{payout:,}** {CURRENCY} 🎉"; color = 0x00FF88
    elif mult == 1.0:
        result = "Bet refunded — break even!"; color = 0xFFD700
    else:
        loss = bet - int(bet * mult)
        u["balance"] -= loss; u["total_lost"] += loss
        result = f"**-{loss:,}** {CURRENCY}"; color = 0xFF4444

    save_data(data)
    await ctx.send(embed=make_embed("🎡 Prize Wheel",
        f"The wheel landed on: **{label}**\n\n{result}\nBalance: **{u['balance']:,}**", color))

# ── HORSE RACE ────────────────────────────────────────────────
HORSES = ["🐎 Thunder", "🐎 Lightning", "🐎 Storm", "🐎 Blaze", "🐎 Shadow"]

@bot.command(name="race")
async def race(ctx, amount: str, horse: int):
    data = load_data()
    u = get_user(data, ctx.author.id)
    bet, err = parse_bet(u, amount)
    if err:
        await ctx.send(embed=make_embed("❌ Error", err, 0xFF4444)); return
    if not 1 <= horse <= 5:
        await ctx.send(embed=make_embed("❌ Error", "Pick horse 1–5.", 0xFF4444)); return

    positions = [0] * 5
    msg = await ctx.send(embed=make_embed("🏇 Horse Race",
        "\n".join(f"**{i+1}. {HORSES[i]}** ░░░░░░░░░░" for i in range(5)) +
        f"\n\nYou bet on **{horse}. {HORSES[horse-1]}**"))

    winner = None
    while winner is None:
        await asyncio.sleep(1.2)
        for i in range(5):
            positions[i] += random.randint(1, 5)
        if max(positions) >= 25:
            winner = positions.index(max(positions))
        track = []
        for i in range(5):
            filled = min(positions[i] * 20 // 25, 20)
            bar = "▓" * filled + "░" * (20 - filled)
            prefix_icon = "🏁" if positions[i] >= 25 else "🐎"
            track.append(f"**{i+1}. {HORSES[i]}** {prefix_icon}{bar}")
        await msg.edit(embed=make_embed("🏇 Horse Race",
            "\n".join(track) + f"\n\nYou bet on **{horse}. {HORSES[horse-1]}**"))

    won = winner == horse - 1
    detail = f"**{HORSES[winner]}** wins!\nYou bet on **{HORSES[horse-1]}**"
    await send_result(ctx, u, won, bet, bet * 4, "🏇 Horse Race Result", detail)
    save_data(data)

# ── TRIVIA ────────────────────────────────────────────────────
TRIVIA_QUESTIONS = [
    ("What is 7 × 8?",                           "56"),
    ("What color do you get mixing red and blue?","purple"),
    ("How many sides does a hexagon have?",       "6"),
    ("What planet is closest to the sun?",        "mercury"),
    ("What is the capital of France?",            "paris"),
    ("How many days are in a leap year?",         "366"),
    ("What gas do plants absorb from the air?",   "carbon dioxide"),
    ("What is the square root of 144?",           "12"),
    ("In what year did WW2 end?",                 "1945"),
    ("What is the largest ocean?",                "pacific"),
    ("How many bones are in the human body?",     "206"),
    ("What is the chemical symbol for gold?",     "au"),
    ("How many continents are on Earth?",         "7"),
    ("What is the fastest land animal?",          "cheetah"),
    ("How many strings does a standard guitar have?", "6"),
]

@bot.command(name="trivia")
@commands.cooldown(1, 30, commands.BucketType.user)
async def trivia(ctx, amount: str):
    data = load_data()
    u = get_user(data, ctx.author.id)
    bet, err = parse_bet(u, amount)
    if err:
        await ctx.send(embed=make_embed("❌ Error", err, 0xFF4444)); return

    q, a = random.choice(TRIVIA_QUESTIONS)
    await ctx.send(embed=make_embed("🧠 Trivia",
        f"{q}\n\nBet: **{bet:,}** {CURRENCY} | You have **15 seconds!**"))

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel
    try:
        response = await bot.wait_for("message", timeout=15.0, check=check)
    except asyncio.TimeoutError:
        await ctx.send(embed=make_embed("🧠 Trivia — Time's Up!", f"The answer was **{a}**.")); return

    won = response.content.strip().lower() == a.lower()
    detail = f"Correct answer: **{a}**\nYou said: **{response.content.strip()}**"
    await send_result(ctx, u, won, bet, bet, "🧠 Trivia", detail)
    save_data(data)

# ── ROB ───────────────────────────────────────────────────────
@bot.command(name="rob", aliases=["steal"])
@commands.cooldown(1, 300, commands.BucketType.user)
async def rob(ctx, target: discord.Member):
    if target.id == ctx.author.id:
        await ctx.send(embed=make_embed("❌ Error", "You can't rob yourself.", 0xFF4444)); return
    data = load_data()
    robber = get_user(data, ctx.author.id)
    victim = get_user(data, target.id)
    if victim["balance"] < 100:
        await ctx.send(embed=make_embed("❌ Rob Failed",
            f"{target.display_name} is too broke to rob.", 0xFF4444)); return

    if random.random() < 0.15:  # 15% success rate (down from 45%)
        stolen = random.randint(50, min(500, victim["balance"] // 4))
        robber["balance"] += stolen
        victim["balance"] -= stolen
        save_data(data)
        await ctx.send(embed=make_embed("🦹 Rob — Success!",
            f"You managed to steal **{stolen:,}** {CURRENCY} from {target.display_name}!\n"
            f"*(You got very lucky — 15% chance!)*", 0x00FF88))
    else:
        fine = random.randint(50, 200)
        robber["balance"] = max(0, robber["balance"] - fine)
        victim["balance"] += fine
        save_data(data)
        await ctx.send(embed=make_embed("🦹 Rob — Caught!",
            f"You got caught and fined **{fine:,}** {CURRENCY}!\n"
            f"The fine went to {target.display_name}.", 0xFF4444))

# ── MINES ─────────────────────────────────────────────────────
@bot.command(name="mines")
async def mines(ctx, amount: str, num_mines: int = 5):
    data = load_data()
    u = get_user(data, ctx.author.id)
    bet, err = parse_bet(u, amount)
    if err:
        await ctx.send(embed=make_embed("❌ Error", err, 0xFF4444)); return
    if not 1 <= num_mines <= 20:
        await ctx.send(embed=make_embed("❌ Error",
            "Bombs must be between **1 and 20**.\nMore bombs = higher multiplier per tile, but riskier!", 0xFF4444)); return

    total_tiles    = 25
    mine_positions = set(random.sample(range(total_tiles), num_mines))
    revealed       = set()
    safe_tiles     = total_tiles - num_mines

    def make_grid(show_mines=False):
        rows = []
        for i in range(5):
            row = []
            for j in range(5):
                idx = i * 5 + j
                if idx in revealed:
                    row.append("💎")
                elif show_mines and idx in mine_positions:
                    row.append("💣")
                else:
                    row.append("⬜")
            rows.append(" ".join(row))
        return "\n".join(rows)

    def calc_mult():
        return round(1 + (num_mines / safe_tiles) * len(revealed) * 1.5, 2)

    msg_obj = await ctx.send(embed=make_embed("💣 Mines",
        f"{make_grid()}\n\n💣 **Bombs:** {num_mines} | 💎 **Safe:** 0/{safe_tiles}\n"
        f"Type a tile number **(1–25)** or `cashout`\nBet: **{bet:,}** {CURRENCY}"))

    u["games_played"] += 1
    while True:
        def chk(m):
            return m.author == ctx.author and m.channel == ctx.channel
        try:
            resp = await bot.wait_for("message", timeout=60.0, check=chk)
        except asyncio.TimeoutError:
            break

        content = resp.content.strip().lower()
        if content == "cashout":
            break
        if not content.isdigit() or not 1 <= int(content) <= 25:
            await ctx.send("Send a number 1–25 or `cashout`.", delete_after=3); continue

        tile = int(content) - 1
        if tile in revealed:
            await ctx.send("Already revealed!", delete_after=3); continue

        revealed.add(tile)
        if tile in mine_positions:
            u["balance"] -= bet; u["total_lost"] += bet
            save_data(data)
            await msg_obj.edit(embed=make_embed("💣 Mines — BOOM! 💥",
                f"{make_grid(True)}\n\nYou hit a mine! **-{bet:,}** {CURRENCY}\n"
                f"Balance: **{u['balance']:,}**", 0xFF4444))
            return

        multiplier = calc_mult()
        if len(revealed) == safe_tiles:
            payout = int(bet * multiplier) - bet
            u["balance"] += payout; u["total_won"] += payout
            add_xp(u, payout // 50); save_data(data)
            await msg_obj.edit(embed=make_embed("💣 Mines — Cleared! 🎉",
                f"{make_grid()}\n\nAll tiles revealed!\n**+{payout:,}** {CURRENCY}\n"
                f"Balance: **{u['balance']:,}**", 0x00FF88))
            return

        await msg_obj.edit(embed=make_embed("💣 Mines",
            f"{make_grid()}\n\n💣 **Bombs:** {num_mines} | 💎 **Safe:** {len(revealed)}/{safe_tiles}\n"
            f"Multiplier: **{multiplier}x** → Payout: **{int(bet*multiplier):,}**\n"
            f"Type a tile number or `cashout`"))

    if revealed:
        multiplier = calc_mult()
        payout = int(bet * multiplier) - bet
        if payout > 0:
            u["balance"] += payout; u["total_won"] += payout
            add_xp(u, payout // 50)
            msg_txt = f"**+{payout:,}** {CURRENCY} cashed out at {multiplier}x!"
            color = 0x00FF88
        else:
            msg_txt = "No profit — bet returned."
            color = 0xFFD700
    else:
        msg_txt = "No tiles revealed — bet returned."
        color = 0xFFD700
    save_data(data)
    await msg_obj.edit(embed=make_embed("💣 Mines — Cashed Out",
        f"{make_grid(True)}\n\n{msg_txt}\nBalance: **{u['balance']:,}**", color))

# ──────────────────────────────────────────────────────────────
# USE-TO-CREATE / TICKET SYSTEM
# ──────────────────────────────────────────────────────────────

async def create_ticket_channel(ctx, req_id: int, amount: int, request_text: str):
    """Creates a private ticket channel visible only to the owner and the requester."""
    if not ctx.guild:
        return None  # DM — skip channel creation

    try:
        owner_member = ctx.guild.get_member(OWNER_ID)
        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(
                read_messages=False, send_messages=False
            ),
            ctx.author: discord.PermissionOverwrite(
                read_messages=True, send_messages=True, attach_files=True
            ),
        }
        if owner_member:
            overwrites[owner_member] = discord.PermissionOverwrite(
                read_messages=True, send_messages=True, manage_channels=True
            )
        if ctx.guild.me:
            overwrites[ctx.guild.me] = discord.PermissionOverwrite(
                read_messages=True, send_messages=True, manage_channels=True
            )

        channel = await ctx.guild.create_text_channel(
            name=f"make-game-ticket",
            overwrites=overwrites,
            topic=f"Game Request #{req_id} by {ctx.author} | {amount:,} coins paid",
            reason=f"Casino game request #{req_id} from {ctx.author}"
        )

        owner_ping = owner_member.mention if owner_member else f"<@{OWNER_ID}>"
        await channel.send(
            content=f"{ctx.author.mention} {owner_ping}",
            embed=make_embed(
                f"🎮 Game Creation Ticket — Request #{req_id}",
                f"**Requester:** {ctx.author.mention} (`{ctx.author}`)\n"
                f"**Amount Paid:** {amount:,} {CURRENCY}\n\n"
                f"**Their Request:**\n> {request_text}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"**Owner:** Use `{PREFIX}fulfill {req_id} <note>` when the game is ready.\n"
                f"Then use `{PREFIX}closeticket` to close this channel.",
                0x9B59B6
            )
        )
        return channel
    except discord.Forbidden:
        return None
    except Exception:
        return None

@bot.command(name="usetocreate", aliases=["create", "request"])
async def use_to_create(ctx, amount: int, *, request_text: str):
    if amount < MINIMUM_CREATE_COST:
        await ctx.send(embed=make_embed("❌ Minimum Not Met",
            f"You need to spend at least **{MINIMUM_CREATE_COST:,}** {CURRENCY} to request a custom game.\n\n"
            f"This gets you a **private ticket channel** where you and the owner can discuss your game idea!",
            0xFF4444))
        return

    data = load_data()
    u = get_user(data, ctx.author.id)
    if u["balance"] < amount:
        await ctx.send(embed=make_embed("❌ Insufficient Funds",
            f"You have **{u['balance']:,}** coins. You need **{amount:,}**.", 0xFF4444)); return

    u["balance"] -= amount
    req_id = len(data.get("requests", [])) + 1
    data.setdefault("requests", []).append({
        "id":        req_id,
        "user_id":   str(ctx.author.id),
        "user_name": str(ctx.author),
        "amount":    amount,
        "request":   request_text,
        "status":    "pending",
        "timestamp": datetime.utcnow().isoformat(),
    })
    save_data(data)

    # DM the owner
    try:
        owner = bot.get_user(OWNER_ID) or await bot.fetch_user(OWNER_ID)
        await owner.send(embed=make_embed(f"📬 New Game Request #{req_id}",
            f"**From:** {ctx.author} (`{ctx.author.id}`)\n"
            f"**Amount paid:** {amount:,} {CURRENCY}\n\n"
            f"**Request:**\n{request_text}\n\n"
            f"A private ticket channel has been created in the server.\n"
            f"Use `{PREFIX}fulfill {req_id}` to mark as done.", 0x9B59B6))
    except:
        pass

    # Create ticket channel
    ticket_channel = await create_ticket_channel(ctx, req_id, amount, request_text)
    channel_note = (f"\n\n📌 **Private ticket channel created:** {ticket_channel.mention}\nOnly you and the owner can see it!"
                    if ticket_channel else
                    "\n\n*(Could not create ticket channel — the bot may need Manage Channels permission.)*")

    await ctx.send(embed=make_embed("✅ Game Request Submitted!",
        f"**Request #{req_id}** has been sent to the owner!\n\n"
        f"💰 You paid: **{amount:,}** {CURRENCY}\n"
        f"📝 **Your request:** {request_text}"
        f"{channel_note}", 0x9B59B6))

@bot.command(name="myrequests")
async def my_requests(ctx):
    data = load_data()
    reqs = [r for r in data.get("requests", []) if r["user_id"] == str(ctx.author.id)]
    if not reqs:
        await ctx.send(embed=make_embed("📬 Your Requests", "You have no requests yet.")); return
    lines = []
    for r in reqs[-10:]:
        icon = "✅" if r["status"] == "fulfilled" else "⏳"
        lines.append(f"{icon} **#{r['id']}** — `{r['request'][:50]}` | {r['amount']:,} {CURRENCY}")
    await ctx.send(embed=make_embed("📬 Your Requests", "\n".join(lines)))

# ──────────────────────────────────────────────────────────────
# OWNER COMMANDS (OWNER ID ONLY)
# ──────────────────────────────────────────────────────────────

def is_owner():
    async def predicate(ctx):
        return ctx.author.id == OWNER_ID
    return commands.check(predicate)

@bot.command(name="requests", aliases=["viewrequests"])
@is_owner()
async def view_requests(ctx, status: str = "pending"):
    data = load_data()
    reqs = [r for r in data.get("requests", []) if r["status"] == status]
    if not reqs:
        await ctx.send(embed=make_embed(f"📬 {status.title()} Requests", "None found.")); return
    lines = [f"**#{r['id']}** | {r['user_name']} | **{r['amount']:,}** {CURRENCY}\n> {r['request'][:80]}"
             for r in reqs[:15]]
    await ctx.send(embed=make_embed(f"📬 {status.title()} Requests ({len(reqs)})", "\n\n".join(lines)))

@bot.command(name="fulfill")
@is_owner()
async def fulfill(ctx, request_id: int, *, note: str = "Your game is ready!"):
    data = load_data()
    req = next((r for r in data.get("requests", []) if r["id"] == request_id), None)
    if not req:
        await ctx.send(embed=make_embed("❌ Error", f"Request #{request_id} not found.", 0xFF4444)); return
    if req["status"] == "fulfilled":
        await ctx.send(embed=make_embed("❌ Already Fulfilled", "This request is already done.", 0xFF8800)); return
    req["status"] = "fulfilled"
    req["fulfillment_note"] = note
    save_data(data)
    try:
        user = bot.get_user(int(req["user_id"])) or await bot.fetch_user(int(req["user_id"]))
        await user.send(embed=make_embed("✅ Your Game Request is Fulfilled!",
            f"**Request #{request_id}:** {req['request']}\n\n**Owner's note:** {note}", 0x00FF88))
    except:
        pass
    await ctx.send(embed=make_embed("✅ Request Fulfilled",
        f"Request **#{request_id}** marked done and user notified.\n"
        f"Use `{PREFIX}closeticket` in the ticket channel to delete it."))

@bot.command(name="closeticket")
@is_owner()
async def close_ticket(ctx):
    """Delete the current ticket channel. Must be used inside a ticket channel."""
    if not ctx.channel.name.startswith("make-game-ticket"):
        await ctx.send(embed=make_embed("❌ Error",
            "This command can only be used inside a `make-game-ticket` channel.", 0xFF4444)); return
    await ctx.send(embed=make_embed("🔒 Closing Ticket", "This channel will be deleted in 5 seconds..."))
    await asyncio.sleep(5)
    try:
        await ctx.channel.delete(reason="Ticket closed by owner.")
    except discord.Forbidden:
        await ctx.send(embed=make_embed("❌ Error", "Missing permission to delete this channel.", 0xFF4444))

@bot.command(name="addcoins")
@is_owner()
async def add_coins(ctx, member: discord.Member, amount: int):
    data = load_data()
    u = get_user(data, member.id)
    u["balance"] += amount
    save_data(data)
    await ctx.send(embed=make_embed("👑 Coins Added",
        f"Added **{amount:,}** {CURRENCY} to {member.display_name}.\nNew balance: **{u['balance']:,}**"))

@bot.command(name="removecoins")
@is_owner()
async def remove_coins(ctx, member: discord.Member, amount: int):
    data = load_data()
    u = get_user(data, member.id)
    u["balance"] = max(0, u["balance"] - amount)
    save_data(data)
    await ctx.send(embed=make_embed("👑 Coins Removed",
        f"Removed **{amount:,}** {CURRENCY} from {member.display_name}.\nNew balance: **{u['balance']:,}**"))

@bot.command(name="setbalance", aliases=["setbal"])
@is_owner()
async def set_balance(ctx, member: discord.Member, amount: int):
    data = load_data()
    u = get_user(data, member.id)
    u["balance"] = max(0, amount)
    save_data(data)
    await ctx.send(embed=make_embed("👑 Balance Set",
        f"{member.display_name}'s balance set to **{amount:,}** {CURRENCY}."))

@bot.command(name="addshopitem")
@is_owner()
async def add_shop_item(ctx, name: str, price: int, *, desc: str):
    data = load_data()
    data.setdefault("shop", {})[name] = {"price": price, "desc": desc}
    save_data(data)
    await ctx.send(embed=make_embed("👑 Item Added",
        f"**{name}** added for **{price:,}** {CURRENCY}\n> {desc}"))

@bot.command(name="removeshopitem")
@is_owner()
async def remove_shop_item(ctx, *, name: str):
    data = load_data()
    shop_data = data.get("shop", {})
    key = next((k for k in shop_data if k.lower() == name.lower()), None)
    if not key:
        await ctx.send(embed=make_embed("❌ Error", f"No item named **{name}**.", 0xFF4444)); return
    del shop_data[key]
    save_data(data)
    await ctx.send(embed=make_embed("👑 Item Removed", f"**{key}** removed from the shop."))

@bot.command(name="broadcast")
@is_owner()
async def broadcast(ctx, *, message: str):
    await ctx.send(embed=make_embed("📢 Announcement", message, 0x9B59B6))

@bot.command(name="resetuser")
@is_owner()
async def reset_user(ctx, member: discord.Member):
    data = load_data()
    uid = str(member.id)
    if uid in data["users"]:
        del data["users"][uid]
    save_data(data)
    await ctx.send(embed=make_embed("👑 User Reset", f"{member.display_name}'s data has been reset."))

# ──────────────────────────────────────────────────────────────
# LAUNCH
# ──────────────────────────────────────────────────────────────

keep_alive()

while True:
    try:
        bot.run(BOT_TOKEN, reconnect=True)
    except discord.errors.LoginFailure:
        print("❌ Invalid token! Update BOT_TOKEN in bot.py or set it as an env variable.")
        break
    except Exception as e:
        print(f"⚠️  Bot crashed: {e} — restarting in 5 seconds...")
        time.sleep(5)
