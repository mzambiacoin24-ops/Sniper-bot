import asyncio
import aiohttp
import time
import random
from datetime import datetime

TELEGRAM_TOKEN = "8778061073:AAFvbdcKusf3P74VLTzdcYa7obV2LrgDXyE"
TELEGRAM_CHAT_ID = "7010983039"
HELIUS_RPC = "https://mainnet.helius-rpc.com/?api-key=04e4a6db-29bd-4b08-99d9-46ad23e9feb1"
JUPITER_API = "https://quote-api.jup.ag/v6"

PUMPFUN_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
SOL_MINT = "So11111111111111111111111111111111111111112"

DRY_RUN = True

BUY_AMOUNT_SOL = 0.05
TAKE_PROFIT_X = 3.0
STOP_LOSS_PCT = 0.30
MAX_HOLD_MINUTES = 20

TOTAL_SUPPLY = 1_000_000_000
GRADUATION_MCAP = 69_000
INITIAL_PRICE = 0.000001

sniped_tokens = {}
processed_sigs = set()
seen_mints = set()

stats = {
    "total_launches": 0,
    "sniped": 0,
    "wins": 0,
    "losses": 0,
    "total_pnl_sol": 0.0,
    "graduated": 0
}

def log(msg):
    now = datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] {msg}")

async def send_telegram(session, msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        await session.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})
    except Exception as e:
        log(f"Telegram error: {e}")

async def helius_rpc(session, method, params):
    try:
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        async with session.post(HELIUS_RPC, json=payload) as r:
            data = await r.json()
            return data.get("result")
    except:
        return None

async def get_sol_price(session):
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd"
        async with session.get(url) as r:
            data = await r.json()
            return float(data["solana"]["usd"])
    except:
        return 85.0

# 🔥 FIXED TOKEN DETECTION (IMPORTANT)
async def parse_new_tokens(session, signature):
    try:
        result = await helius_rpc(session, "getTransaction", [
            signature,
            {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}
        ])

        if not result:
            return []

        meta = result.get("meta", {})
        if meta.get("err"):
            return []

        instructions = result.get("transaction", {}).get("message", {}).get("instructions", [])

        new_tokens = []

        for inst in instructions:
            if isinstance(inst, dict):
                program_id = inst.get("programId", "")

                if "token" in program_id.lower():
                    parsed = inst.get("parsed", {})
                    info = parsed.get("info", {})

                    mint = info.get("mint")
                    owner = info.get("owner")

                    if mint and mint not in seen_mints and mint != SOL_MINT:
                        seen_mints.add(mint)
                        new_tokens.append({
                            "mint": mint,
                            "owner": owner or "Unknown"
                        })

        return new_tokens

    except Exception as e:
        log(f"Parse error: {e}")
        return []

async def simulate_bonding_curve_trade(session, token_mint, creator):
    if token_mint in sniped_tokens:
        return

    sol_price = await get_sol_price(session)

    entry_price_usd = INITIAL_PRICE
    tokens_bought = (BUY_AMOUNT_SOL * sol_price) / entry_price_usd

    stats["sniped"] += 1

    sniped_tokens[token_mint] = {
        "entry_price_usd": entry_price_usd,
        "tokens_bought": tokens_bought,
        "entry_time": time.time(),
        "creator": creator or "Unknown",
        "buy_sol": BUY_AMOUNT_SOL,
        "sold": False
    }

    msg = (
        f"🚀 SNIPE!\n"
        f"🪙 Token: {token_mint[:8]}...\n"
        f"👤 Creator: {(creator or 'Unknown')[:8]}...\n"
        f"💰 Buy: {BUY_AMOUNT_SOL} SOL"
    )
    log(msg)
    await send_telegram(session, msg)

async def poll_pumpfun(session):
    log("Inaanza polling Pump.fun...")
    await send_telegram(session, "🎯 Sniper imeanza...")

    last_sig = None

    while True:
        try:
            params = [PUMPFUN_PROGRAM, {"limit": 20, "commitment": "confirmed"}]

            if last_sig:
                params[1]["until"] = last_sig

            sigs = await helius_rpc(session, "getSignaturesForAddress", params)

            if not sigs:
                await asyncio.sleep(2)
                continue

            if last_sig is None:
                last_sig = sigs[0]["signature"]
                log("Imeanza kusubiri tokens mpya...")
                await asyncio.sleep(2)
                continue

            new_sigs = []
            for s in sigs:
                if s["signature"] == last_sig:
                    break
                if not s.get("err"):
                    new_sigs.append(s["signature"])

            if new_sigs:
                last_sig = sigs[0]["signature"]

                for sig in new_sigs[:5]:
                    if sig in processed_sigs:
                        continue

                    processed_sigs.add(sig)

                    new_tokens = await parse_new_tokens(session, sig)

                    for token_info in new_tokens:
                        stats["total_launches"] += 1
                        log(f"🆕 Token #{stats['total_launches']}")
                        await simulate_bonding_curve_trade(
                            session,
                            token_info["mint"],
                            token_info["owner"]
                        )

            await asyncio.sleep(2)

        except Exception as e:
            log(f"Poll error: {e}")
            await asyncio.sleep(5)

async def print_stats(session):
    while True:
        await asyncio.sleep(300)
        msg = (
            f"📊 Launches: {stats['total_launches']}\n"
            f"🎯 Sniped: {stats['sniped']}"
        )
        await send_telegram(session, msg)

async def main():
    async with aiohttp.ClientSession() as session:
        await send_telegram(session, "🚀 BOT STARTED")

        await asyncio.gather(
            poll_pumpfun(session),
            print_stats(session)
        )

if __name__ == "__main__":
    asyncio.run(main())
