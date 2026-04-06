import asyncio
import aiohttp
import time
from datetime import datetime

TELEGRAM_TOKEN = "8778061073:AAFvbdcKusf3P74VLTzdcYa7obV2LrgDXyE"
TELEGRAM_CHAT_ID = "7010983039"
HELIUS_RPC = "https://mainnet.helius-rpc.com/?api-key=04e4a6db-29bd-4b08-99d9-46ad23e9feb1"
HELIUS_KEY = "04e4a6db-29bd-4b08-99d9-46ad23e9feb1"
JUPITER_API = "https://quote-api.jup.ag/v6"

PUMPFUN_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
SOL_MINT = "So11111111111111111111111111111111111111112"

DRY_RUN = True

BUY_AMOUNT_SOL = 0.05
MAX_PRICE_IMPACT_PCT = 25
TAKE_PROFIT_X = 3.0
STOP_LOSS_PCT = 0.30
MAX_HOLD_MINUTES = 30

sniped_tokens = {}
processed_sigs = set()
stats = {
    "total_launches": 0,
    "sniped": 0,
    "wins": 0,
    "losses": 0,
    "total_pnl": 0.0
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

async def get_token_price(session, token_mint):
    try:
        url = f"https://price.jup.ag/v4/price?ids={token_mint}"
        async with session.get(url) as r:
            data = await r.json()
            return float(data.get("data", {}).get(token_mint, {}).get("price", 0))
    except:
        return 0.0

async def is_honeypot(session, token_mint):
    try:
        url = (
            f"{JUPITER_API}/quote?"
            f"inputMint={token_mint}"
            f"&outputMint={SOL_MINT}"
            f"&amount=1000000"
            f"&slippageBps=2500"
        )
        async with session.get(url) as r:
            if r.status != 200:
                return True
            data = await r.json()
            impact = float(data.get("priceImpactPct", 100))
            return impact > MAX_PRICE_IMPACT_PCT
    except:
        return True

async def get_new_pumpfun_tokens(session, last_sig):
    try:
        params = [
            PUMPFUN_PROGRAM,
            {"limit": 20, "commitment": "confirmed"}
        ]
        if last_sig:
            params[1]["until"] = last_sig

        result = await helius_rpc(session, "getSignaturesForAddress", params)
        return result if result else []
    except:
        return []

async def parse_token_from_tx(session, signature):
    try:
        result = await helius_rpc(session, "getTransaction", [
            signature,
            {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}
        ])
        if not result:
            return None, None

        meta = result.get("meta", {})
        if meta.get("err"):
            return None, None

        log_messages = meta.get("logMessages", [])

        is_new = any(
            "create" in m.lower() or
            "initialize" in m.lower() or
            "mint" in m.lower()
            for m in log_messages
        )

        if not is_new:
            return None, None

        accounts = result.get("transaction", {}).get("message", {}).get("accountKeys", [])
        creator = None
        for acc in accounts:
            if isinstance(acc, dict) and acc.get("signer"):
                creator = acc.get("pubkey")
                break

        post_balances = meta.get("postTokenBalances", [])
        pre_balances = meta.get("preTokenBalances", [])
        pre_mints = {b["mint"] for b in pre_balances}

        new_mints = [
            b["mint"] for b in post_balances
            if b["mint"] not in pre_mints
        ]

        if new_mints:
            return new_mints[0], creator

        if post_balances:
            return post_balances[0]["mint"], creator

        return None, None

    except:
        return None, None

async def snipe_token(session, token_mint, creator):
    if token_mint in sniped_tokens:
        return

    honeypot = await is_honeypot(session, token_mint)
    if honeypot:
        log(f"Honeypot imezuiwa: {token_mint[:8]}...")
        return

    sol_price = await get_sol_price(session)
    entry_price = await get_token_price(session, token_mint)
    usd_value = BUY_AMOUNT_SOL * sol_price
    stats["sniped"] += 1

    sniped_tokens[token_mint] = {
        "entry_price": entry_price,
        "entry_time": time.time(),
        "creator": creator or "Unknown",
        "buy_sol": BUY_AMOUNT_SOL,
        "sold": False
    }

    msg = (
        f"🚀 EARLY SNIPE!\n"
        f"🪙 Token: {token_mint[:8]}...\n"
        f"👤 Creator: {(creator or 'Unknown')[:8]}...\n"
        f"💰 Kununua: {BUY_AMOUNT_SOL} SOL (${usd_value:.1f})\n"
        f"💲 Bei entry: ${entry_price:.10f}\n"
        f"🎯 TP: {TAKE_PROFIT_X}x | SL: -{STOP_LOSS_PCT*100:.0f}%\n"
        f"🧪 SIMULATION"
    )
    log(msg)
    await send_telegram(session, msg)
    asyncio.create_task(monitor_position(session, token_mint))

async def monitor_position(session, token_mint):
    await asyncio.sleep(15)

    if token_mint not in sniped_tokens:
        return

    position = sniped_tokens[token_mint]
    entry_price = position["entry_price"]

    if entry_price <= 0:
        position["sold"] = True
        return

    while not position["sold"]:
        try:
            current_price = await get_token_price(session, token_mint)
            elapsed_min = (time.time() - position["entry_time"]) / 60

            if current_price <= 0:
                await asyncio.sleep(15)
                continue

            multiplier = current_price / entry_price
            change_pct = (multiplier - 1) * 100

            if multiplier >= TAKE_PROFIT_X:
                pnl = position["buy_sol"] * (multiplier - 1)
                stats["wins"] += 1
                stats["total_pnl"] += pnl
                position["sold"] = True
                sol_price = await get_sol_price(session)
                msg = (
                    f"💰 TAKE PROFIT!\n"
                    f"🪙 {token_mint[:8]}...\n"
                    f"📈 {multiplier:.1f}x (+{change_pct:.0f}%)\n"
                    f"💵 PnL: +{pnl:.4f} SOL (${pnl*sol_price:.1f})\n"
                    f"📊 Total PnL: {stats['total_pnl']:.4f} SOL\n"
                    f"🧪 SIMULATION"
                )
                await send_telegram(session, msg)
                break

            elif (1 - multiplier) >= STOP_LOSS_PCT:
                pnl = -position["buy_sol"] * STOP_LOSS_PCT
                stats["losses"] += 1
                stats["total_pnl"] += pnl
                position["sold"] = True
                msg = (
                    f"🛑 STOP LOSS!\n"
                    f"🪙 {token_mint[:8]}...\n"
                    f"📉 {change_pct:.0f}%\n"
                    f"💸 PnL: {pnl:.4f} SOL\n"
                    f"📊 Total PnL: {stats['total_pnl']:.4f} SOL\n"
                    f"🧪 SIMULATION"
                )
                await send_telegram(session, msg)
                break

            elif elapsed_min >= MAX_HOLD_MINUTES:
                pnl = position["buy_sol"] * (multiplier - 1)
                if pnl > 0:
                    stats["wins"] += 1
                else:
                    stats["losses"] += 1
                stats["total_pnl"] += pnl
                position["sold"] = True
                sol_price = await get_sol_price(session)
                msg = (
                    f"⏱️ MUDA UMEISHA!\n"
                    f"🪙 {token_mint[:8]}...\n"
                    f"📊 {multiplier:.2f}x ({change_pct:+.1f}%)\n"
                    f"💵 PnL: {pnl:+.4f} SOL (${pnl*sol_price:.1f})\n"
                    f"📊 Total PnL: {stats['total_pnl']:.4f} SOL\n"
                    f"🧪 SIMULATION"
                )
                await send_telegram(session, msg)
                break

            await asyncio.sleep(15)

        except Exception as e:
            log(f"Monitor error: {e}")
            await asyncio.sleep(15)

async def poll_pumpfun(session):
    log("Inaanza polling Pump.fun...")
    await send_telegram(session, "🔍 Bot inaangalia Pump.fun kwa polling...")

    last_sig = None

    while True:
        try:
            sigs = await get_new_pumpfun_tokens(session, last_sig)

            if sigs:
                if last_sig is None:
                    last_sig = sigs[0]["signature"]
                    log(f"Initialized. Inaanza kufuatilia...")
                    await asyncio.sleep(3)
                    continue

                new_sigs = []
                for s in sigs:
                    if s["signature"] == last_sig:
                        break
                    new_sigs.append(s["signature"])

                if new_sigs:
                    last_sig = sigs[0]["signature"]
                    log(f"Transactions mpya {len(new_sigs)} zimepatikana!")

                    for sig in new_sigs[:5]:
                        if sig not in processed_sigs:
                            processed_sigs.add(sig)
                            token_mint, creator = await parse_token_from_tx(session, sig)

                            if token_mint:
                                stats["total_launches"] += 1
                                log(f"Token mpya: {token_mint[:8]}...")
                                await snipe_token(session, token_mint, creator)

            await asyncio.sleep(2)

        except Exception as e:
            log(f"Poll error: {e}")
            await asyncio.sleep(5)

async def print_stats(session):
    while True:
        await asyncio.sleep(300)
        sol_price = await get_sol_price(session)
        win_rate = (stats["wins"] / max(stats["sniped"], 1)) * 100
        msg = (
            f"📊 RIPOTI YA DAKIKA 5\n"
            f"🚀 Launches: {stats['total_launches']}\n"
            f"🎯 Sniped: {stats['sniped']}\n"
            f"✅ Wins: {stats['wins']} | ❌ Losses: {stats['losses']}\n"
            f"📈 Win Rate: {win_rate:.1f}%\n"
            f"💰 Total PnL: {stats['total_pnl']:.4f} SOL (${stats['total_pnl']*sol_price:.1f})\n"
            f"🧪 SIMULATION"
        )
        log(msg)
        await send_telegram(session, msg)

async def main():
    async with aiohttp.ClientSession() as session:
        sol_price = await get_sol_price(session)
        start_msg = (
            f"🎯 PUMP.FUN EARLY SNIPER V2!\n"
            f"🔄 Method: Polling (hakuna WebSocket)\n"
            f"💰 Buy: {BUY_AMOUNT_SOL} SOL (${BUY_AMOUNT_SOL*sol_price:.1f})\n"
            f"🎯 Take Profit: {TAKE_PROFIT_X}x\n"
            f"🛑 Stop Loss: -{STOP_LOSS_PCT*100:.0f}%\n"
            f"⏱️ Max Hold: {MAX_HOLD_MINUTES} dakika\n"
            f"🧪 Mode: {'SIMULATION' if DRY_RUN else 'LIVE'}"
        )
        log(start_msg)
        await send_telegram(session, start_msg)

        await asyncio.gather(
            poll_pumpfun(session),
            print_stats(session)
        )

if __name__ == "__main__":
    asyncio.run(main())
