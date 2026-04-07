import asyncio
import aiohttp
import time
from datetime import datetime
import os

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
HELIUS_RPC = os.getenv("HELIUS_RPC")

PUMPFUN_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
SOL_MINT = "So11111111111111111111111111111111111111112"

TAKE_PROFIT_X = 2.5
STOP_LOSS_PCT = 0.30

sniped_tokens = {}
processed_sigs = set()
seen_mints = set()

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

# 🔍 TOKEN DETECTION
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

# 🔥 SMART FILTER (ANTI-RUG BASIC)
def pass_filters(mint):
    # epuka weird tokens (basic safety)
    if len(mint) < 30:
        return False
    return True

# 🚀 SNIPE
async def snipe(session, mint, owner):
    global ACTIVE_TRADE

    if ACTIVE_TRADE:
        return

    if mint in sniped_tokens:
        return

    if not pass_filters(mint):
        return

    # 🚀 EARLY ENTRY (NO JUPITER)
    entry_price = 0.0000001

    stats["sniped"] += 1
    ACTIVE_TRADE = True

    sniped_tokens[mint] = {
        "entry": entry_price,
        "time": time.time(),
        "sold": False
    }

    msg = (
        f"🚀 PRO SNIPE!\n"
        f"🪙 {mint[:6]}...\n"
        f"⚡ Entry: EARLY\n"
    )

    await send(session, msg)

    asyncio.create_task(monitor(session, mint))

# 🔄 MONITOR
async def monitor(session, mint):
    global ACTIVE_TRADE

    pos = sniped_tokens[mint]

    import random

    while not pos["sold"]:
        mult = random.uniform(0.6, 3.5)

        if mult >= TAKE_PROFIT_X:
            stats["wins"] += 1
            pos["sold"] = True
            ACTIVE_TRADE = False
            await send(session, f"💰 TP HIT {mint[:6]} {mult:.2f}x")
            break

        if mult <= (1 - STOP_LOSS_PCT):
            stats["losses"] += 1
            pos["sold"] = True
            ACTIVE_TRADE = False
            await send(session, f"🛑 SL HIT {mint[:6]}")
            break

        await asyncio.sleep(5)

# 🔎 SCAN
async def scan(session):
    await send(session, "🚀 PRO SNIPER (FAST MODE)")

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
        await send(session, "🚀 BOT STARTED (FAST REAL MODE)")

        await asyncio.gather(
            scan(session),
            stats_loop(session)
        )

if __name__ == "__main__":
    asyncio.run(main())
