import asyncio
import aiohttp
import time
from datetime import datetime

TELEGRAM_TOKEN = "8778061073:AAFvbdcKusf3P74VLTzdcYa7obV2LrgDXyE"
TELEGRAM_CHAT_ID = "7010983039"
HELIUS_RPC = "https://mainnet.helius-rpc.com/?api-key=04e4a6db-29bd-4b08-99d9-46ad23e9feb1"

JUPITER_API = "https://price.jup.ag/v4/price"

PUMPFUN_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
SOL_MINT = "So11111111111111111111111111111111111111112"

BUY_AMOUNT_SOL = 0.05
TAKE_PROFIT_X = 2.0
STOP_LOSS_PCT = 0.30
MAX_HOLD_MINUTES = 20

sniped_tokens = {}
processed_sigs = set()
seen_mints = set()

stats = {
    "total_launches": 0,
    "sniped": 0,
    "wins": 0,
    "losses": 0,
    "total_pnl_sol": 0.0
}

def log(msg):
    now = datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] {msg}")

async def send_telegram(session, msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    await session.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})

async def helius_rpc(session, method, params):
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    async with session.post(HELIUS_RPC, json=payload) as r:
        data = await r.json()
        return data.get("result")

# 🔥 REAL PRICE kutoka Jupiter
async def get_token_price(session, mint):
    try:
        url = f"{JUPITER_API}?ids={mint}"
        async with session.get(url) as r:
            data = await r.json()
            return float(data["data"][mint]["price"])
    except:
        return None

# 🔥 TOKEN DETECTION (REAL)
async def parse_new_tokens(session, signature):
    try:
        result = await helius_rpc(session, "getTransaction", [
            signature,
            {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}
        ])

        if not result:
            return []

        instructions = result.get("transaction", {}).get("message", {}).get("instructions", [])

        tokens = []

        for inst in instructions:
            if isinstance(inst, dict):
                parsed = inst.get("parsed", {})
                info = parsed.get("info", {})

                mint = info.get("mint")
                owner = info.get("owner")

                if mint and mint != SOL_MINT and mint not in seen_mints:
                    seen_mints.add(mint)
                    tokens.append({"mint": mint, "owner": owner or "Unknown"})

        return tokens

    except:
        return []

# 🚀 SIMULATION ENTRY
async def simulate_trade(session, mint, creator):
    if mint in sniped_tokens:
        return

    price = await get_token_price(session, mint)

    if not price:
        return

    stats["sniped"] += 1

    sniped_tokens[mint] = {
        "entry_price": price,
        "entry_time": time.time(),
        "sold": False
    }

    msg = (
        f"🚀 SNIPE REAL TOKEN!\n"
        f"🪙 {mint[:8]}...\n"
        f"👤 {creator[:8]}...\n"
        f"💲 Price: ${price:.8f}\n"
        f"🧪 SIMULATION"
    )

    log(msg)
    await send_telegram(session, msg)

    asyncio.create_task(monitor_trade(session, mint))

# 🔄 MONITOR REAL PRICE
async def monitor_trade(session, mint):
    await asyncio.sleep(5)

    pos = sniped_tokens[mint]
    entry = pos["entry_price"]

    while not pos["sold"]:
        try:
            price = await get_token_price(session, mint)

            if not price:
                await asyncio.sleep(5)
                continue

            multiplier = price / entry

            if multiplier >= TAKE_PROFIT_X:
                stats["wins"] += 1
                pos["sold"] = True

                await send_telegram(session, f"💰 TP HIT {mint[:6]} {multiplier:.2f}x")
                break

            elif (1 - multiplier) >= STOP_LOSS_PCT:
                stats["losses"] += 1
                pos["sold"] = True

                await send_telegram(session, f"🛑 SL HIT {mint[:6]}")
                break

            await asyncio.sleep(5)

        except:
            await asyncio.sleep(5)

# 🔎 SCAN PUMPFUN
async def poll_pumpfun(session):
    await send_telegram(session, "🎯 REAL SNIPER STARTED")

    last_sig = None

    while True:
        try:
            params = [PUMPFUN_PROGRAM, {"limit": 20}]

            if last_sig:
                params[1]["until"] = last_sig

            sigs = await helius_rpc(session, "getSignaturesForAddress", params)

            if not sigs:
                await asyncio.sleep(2)
                continue

            if last_sig is None:
                last_sig = sigs[0]["signature"]
                await asyncio.sleep(2)
                continue

            new_sigs = []

            for s in sigs:
                if s["signature"] == last_sig:
                    break
                new_sigs.append(s["signature"])

            if new_sigs:
                last_sig = sigs[0]["signature"]

                for sig in new_sigs[:5]:
                    if sig in processed_sigs:
                        continue

                    processed_sigs.add(sig)

                    tokens = await parse_new_tokens(session, sig)

                    for t in tokens:
                        stats["total_launches"] += 1
                        await simulate_trade(session, t["mint"], t["owner"])

            await asyncio.sleep(2)

        except Exception as e:
            log(f"Error: {e}")
            await asyncio.sleep(5)

# 📊 STATS
async def print_stats(session):
    while True:
        await asyncio.sleep(300)

        msg = (
            f"📊 Launches: {stats['total_launches']}\n"
            f"🎯 Sniped: {stats['sniped']}\n"
            f"✅ Wins: {stats['wins']} | ❌ Losses: {stats['losses']}"
        )

        await send_telegram(session, msg)

async def main():
    async with aiohttp.ClientSession() as session:
        await send_telegram(session, "🚀 BOT STARTED (REAL DATA)")

        await asyncio.gather(
            poll_pumpfun(session),
            print_stats(session)
        )

if __name__ == "__main__":
    asyncio.run(main())
