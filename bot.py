import asyncio
import aiohttp
import time
from datetime import datetime

TELEGRAM_TOKEN = "8778061073:AAFvbdcKusf3P74VLTzdcYa7obV2LrgDXyE"
TELEGRAM_CHAT_ID = "7010983039"
HELIUS_RPC = "https://mainnet.helius-rpc.com/?api-key=04e4a6db-29bd-4b08-99d9-46ad23e9feb1"

PUMPFUN_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
SOL_MINT = "So11111111111111111111111111111111111111112"

BUY_AMOUNT_SOL = 0.05
TAKE_PROFIT_X = 2.5
STOP_LOSS_PCT = 0.35

sniped_tokens = {}
processed_sigs = set()
seen_mints = set()

# 🔒 SINGLE TRADE CONTROL
ACTIVE_TRADE = False

stats = {
    "launches": 0,
    "sniped": 0,
    "wins": 0,
    "losses": 0
}

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

async def send(session, msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    await session.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})

async def helius(session, method, params):
    payload = {"jsonrpc":"2.0","id":1,"method":method,"params":params}
    async with session.post(HELIUS_RPC, json=payload) as r:
        data = await r.json()
        return data.get("result")

# 🔥 TOKEN DETECTION
async def get_tokens(session, sig):
    try:
        tx = await helius(session, "getTransaction", [sig, {"encoding":"jsonParsed"}])
        if not tx:
            return []

        instructions = tx["transaction"]["message"]["instructions"]
        tokens = []

        for i in instructions:
            info = i.get("parsed", {}).get("info", {})
            mint = info.get("mint")
            owner = info.get("owner")

            if mint and mint != SOL_MINT and mint not in seen_mints:
                seen_mints.add(mint)
                tokens.append((mint, owner or "unknown"))

        return tokens
    except:
        return []

# 🔥 SIMULATION METRICS (PRO LOGIC)
def generate_metrics():
    import random
    buyers = random.randint(20, 300)
    volume = random.uniform(1, 15)
    mcap = random.uniform(3000, 40000)
    momentum = random.uniform(0, 1)
    return buyers, volume, mcap, momentum

# 🔥 FILTER
def pass_filters(buyers, volume, mcap, momentum):
    if buyers < 80:
        return False
    if volume < 3:
        return False
    if mcap < 5000 or mcap > 50000:
        return False
    if momentum < 0.4:
        return False
    return True

# 🚀 SNIPE (SINGLE TRADE MODE)
async def snipe(session, mint, owner):
    global ACTIVE_TRADE

    # 🔒 kama kuna trade inaendelea → skip
    if ACTIVE_TRADE:
        return

    if mint in sniped_tokens:
        return

    buyers, volume, mcap, momentum = generate_metrics()

    if not pass_filters(buyers, volume, mcap, momentum):
        return

    entry_price = 0.0000001

    stats["sniped"] += 1
    ACTIVE_TRADE = True  # 🔒 lock

    sniped_tokens[mint] = {
        "entry": entry_price,
        "time": time.time(),
        "sold": False
    }

    msg = (
        f"🚀 PRO SNIPE!\n"
        f"🪙 {mint[:6]}...\n"
        f"👥 Buyers: {buyers}\n"
        f"💰 Volume: {volume:.2f} SOL\n"
        f"📊 MCap: ${mcap:,.0f}\n"
        f"⚡ Momentum: {momentum:.2f}\n"
        f"🎯 Entry: simulated\n"
    )

    await send(session, msg)

    asyncio.create_task(monitor(session, mint))

# 🔄 MONITOR (UNLOCK AFTER SELL)
async def monitor(session, mint):
    global ACTIVE_TRADE

    await asyncio.sleep(5)

    pos = sniped_tokens[mint]

    import random

    while not pos["sold"]:
        mult = random.uniform(0.5, 3.5)

        if mult >= TAKE_PROFIT_X:
            stats["wins"] += 1
            pos["sold"] = True
            ACTIVE_TRADE = False  # 🔓 unlock
            await send(session, f"💰 TP HIT {mint[:6]} {mult:.2f}x")
            break

        if mult <= (1 - STOP_LOSS_PCT):
            stats["losses"] += 1
            pos["sold"] = True
            ACTIVE_TRADE = False  # 🔓 unlock
            await send(session, f"🛑 SL HIT {mint[:6]}")
            break

        await asyncio.sleep(5)

# 🔎 SCAN
async def scan(session):
    await send(session, "🚀 PRO SNIPER STARTED")

    last = None

    while True:
        try:
            sigs = await helius(session, "getSignaturesForAddress", [PUMPFUN_PROGRAM, {"limit":20}])

            if not sigs:
                await asyncio.sleep(2)
                continue

            if not last:
                last = sigs[0]["signature"]
                await asyncio.sleep(2)
                continue

            new = []

            for s in sigs:
                if s["signature"] == last:
                    break
                new.append(s["signature"])

            if new:
                last = sigs[0]["signature"]

                for sig in new[:5]:
                    if sig in processed_sigs:
                        continue

                    processed_sigs.add(sig)

                    tokens = await get_tokens(session, sig)

                    for mint, owner in tokens:
                        stats["launches"] += 1
                        await snipe(session, mint, owner)

            await asyncio.sleep(2)

        except Exception as e:
            log(e)
            await asyncio.sleep(5)

# 📊 REPORT
async def stats_loop(session):
    while True:
        await asyncio.sleep(300)
        msg = (
            f"📊 PRO REPORT\n"
            f"🚀 Launches: {stats['launches']}\n"
            f"🎯 Sniped: {stats['sniped']}\n"
            f"✅ Wins: {stats['wins']} | ❌ Losses: {stats['losses']}"
        )
        await send(session, msg)

async def main():
    async with aiohttp.ClientSession() as session:
        await send(session, "🚀 BOT STARTED (PRO SINGLE TRADE MODE)")

        await asyncio.gather(
            scan(session),
            stats_loop(session)
        )

if __name__ == "__main__":
    asyncio.run(main())
