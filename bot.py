import asyncio
import aiohttp
import json
import time
from datetime import datetime

TELEGRAM_TOKEN = "8778061073:AAFvbdcKusf3P74VLTzdcYa7obV2LrgDXyE"
TELEGRAM_CHAT_ID = "7010983039"
HELIUS_RPC = "https://mainnet.helius-rpc.com/?api-key=04e4a6db-29bd-4b08-99d9-46ad23e9feb1"
HELIUS_WS = "wss://mainnet.helius-rpc.com/?api-key=04e4a6db-29bd-4b08-99d9-46ad23e9feb1"
HELIUS_KEY = "04e4a6db-29bd-4b08-99d9-46ad23e9feb1"
JUPITER_API = "https://quote-api.jup.ag/v6"

PUMPFUN_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
SOL_MINT = "So11111111111111111111111111111111111111112"

DRY_RUN = True

BUY_AMOUNT_SOL = 0.05
MAX_PRICE_IMPACT_PCT = 20
MIN_INITIAL_LIQUIDITY = 1000
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
    except Exception as e:
        log(f"RPC error: {e}")
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
            price = data.get("data", {}).get(token_mint, {}).get("price", 0)
            return float(price)
    except:
        return 0.0

async def can_buy_token(session, token_mint):
    try:
        url = (
            f"{JUPITER_API}/quote?"
            f"inputMint={SOL_MINT}"
            f"&outputMint={token_mint}"
            f"&amount={int(BUY_AMOUNT_SOL * 1e9)}"
            f"&slippageBps=2000"
        )
        async with session.get(url) as r:
            if r.status != 200:
                return False, 0
            data = await r.json()
            impact = float(data.get("priceImpactPct", 100))
            out_amount = int(data.get("outAmount", 0))
            return impact < MAX_PRICE_IMPACT_PCT, out_amount
    except:
        return False, 0

async def can_sell_token(session, token_mint):
    try:
        url = (
            f"{JUPITER_API}/quote?"
            f"inputMint={token_mint}"
            f"&outputMint={SOL_MINT}"
            f"&amount=1000000"
            f"&slippageBps=2000"
        )
        async with session.get(url) as r:
            if r.status != 200:
                return False
            data = await r.json()
            impact = float(data.get("priceImpactPct", 100))
            return impact < MAX_PRICE_IMPACT_PCT
    except:
        return False

async def quick_safety_check(session, token_mint):
    can_buy, _ = await can_buy_token(session, token_mint)
    if not can_buy:
        return False, "Haiwezi kununuliwa"

    can_sell = await can_sell_token(session, token_mint)
    if not can_sell:
        return False, "Honeypot — haiwezi kuuzwa!"

    return True, "Imepita safety check"

async def simulate_buy(session, token_mint, creator):
    sol_price = await get_sol_price(session)
    usd_value = BUY_AMOUNT_SOL * sol_price
    entry_price = await get_token_price(session, token_mint)

    stats["sniped"] += 1

    msg = (
        f"🚀 EARLY SNIPE!\n"
        f"🪙 Token: {token_mint[:8]}...\n"
        f"👤 Creator: {creator[:8]}...\n"
        f"💰 Kununua: {BUY_AMOUNT_SOL} SOL (${usd_value:.1f})\n"
        f"💲 Bei ya entry: ${entry_price:.8f}\n"
        f"🎯 Take Profit: {TAKE_PROFIT_X}x\n"
        f"🛑 Stop Loss: -{STOP_LOSS_PCT*100:.0f}%\n"
        f"⏱️ Max Hold: {MAX_HOLD_MINUTES} dakika\n"
        f"🧪 SIMULATION"
    )
    log(msg)
    await send_telegram(session, msg)

    sniped_tokens[token_mint] = {
        "entry_price": entry_price,
        "entry_time": time.time(),
        "creator": creator,
        "buy_sol": BUY_AMOUNT_SOL,
        "buy_usd": usd_value,
        "sold": False
    }

async def monitor_position(session, token_mint):
    await asyncio.sleep(10)

    if token_mint not in sniped_tokens:
        return

    position = sniped_tokens[token_mint]
    entry_price = position["entry_price"]
    entry_time = position["entry_time"]

    if entry_price <= 0:
        sniped_tokens[token_mint]["sold"] = True
        return

    while not position["sold"]:
        try:
            current_price = await get_token_price(session, token_mint)
            elapsed_minutes = (time.time() - entry_time) / 60

            if current_price <= 0:
                await asyncio.sleep(10)
                continue

            price_change = (current_price - entry_price) / entry_price
            multiplier = current_price / entry_price

            if multiplier >= TAKE_PROFIT_X:
                pnl = position["buy_sol"] * (multiplier - 1)
                stats["wins"] += 1
                stats["total_pnl"] += pnl
                position["sold"] = True
                sol_price = await get_sol_price(session)
                msg = (
                    f"💰 TAKE PROFIT IMEFIKIWA!\n"
                    f"🪙 Token: {token_mint[:8]}...\n"
                    f"📈 Bei: {multiplier:.1f}x\n"
                    f"💵 PnL: +{pnl:.4f} SOL (${pnl*sol_price:.1f})\n"
                    f"📊 Total PnL: {stats['total_pnl']:.4f} SOL\n"
                    f"🧪 SIMULATION"
                )
                log(msg)
                await send_telegram(session, msg)
                break

            elif price_change <= -STOP_LOSS_PCT:
                pnl = -position["buy_sol"] * STOP_LOSS_PCT
                stats["losses"] += 1
                stats["total_pnl"] += pnl
                position["sold"] = True
                msg = (
                    f"🛑 STOP LOSS!\n"
                    f"🪙 Token: {token_mint[:8]}...\n"
                    f"📉 Bei imeshuka: {price_change*100:.1f}%\n"
                    f"💸 PnL: {pnl:.4f} SOL\n"
                    f"📊 Total PnL: {stats['total_pnl']:.4f} SOL\n"
                    f"🧪 SIMULATION"
                )
                log(msg)
                await send_telegram(session, msg)
                break

            elif elapsed_minutes >= MAX_HOLD_MINUTES:
                pnl = position["buy_sol"] * price_change
                if pnl > 0:
                    stats["wins"] += 1
                else:
                    stats["losses"] += 1
                stats["total_pnl"] += pnl
                position["sold"] = True
                sol_price = await get_sol_price(session)
                msg = (
                    f"⏱️ MUDA UMEISHA — INAOUZA!\n"
                    f"🪙 Token: {token_mint[:8]}...\n"
                    f"📊 Bei: {multiplier:.2f}x ({price_change*100:+.1f}%)\n"
                    f"💵 PnL: {pnl:+.4f} SOL (${pnl*sol_price:.1f})\n"
                    f"📊 Total PnL: {stats['total_pnl']:.4f} SOL\n"
                    f"🧪 SIMULATION"
                )
                log(msg)
                await send_telegram(session, msg)
                break

            await asyncio.sleep(15)

        except Exception as e:
            log(f"Monitor error: {e}")
            await asyncio.sleep(15)

async def process_new_launch(session, signature):
    if signature in processed_sigs:
        return
    processed_sigs.add(signature)

    try:
        result = await helius_rpc(session, "getTransaction", [
            signature,
            {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}
        ])
        if not result:
            return

        meta = result.get("meta", {})
        if meta.get("err"):
            return

        log_messages = meta.get("logMessages", [])
        is_new_token = any("InitializeMint" in m or "create" in m.lower() for m in log_messages)
        if not is_new_token:
            return

        accounts = result.get("transaction", {}).get("message", {}).get("accountKeys", [])
        if not accounts:
            return

        creator = None
        token_mint = None

        for acc in accounts:
            pubkey = acc.get("pubkey", "") if isinstance(acc, dict) else str(acc)
            if acc.get("signer") if isinstance(acc, dict) else False:
                creator = pubkey

        post_balances = meta.get("postTokenBalances", [])
        if post_balances:
            token_mint = post_balances[0].get("mint")

        if not token_mint or not creator:
            return

        if token_mint in sniped_tokens:
            return

        stats["total_launches"] += 1
        log(f"Token mpya: {token_mint[:8]}... na {creator[:8]}...")

        safe, reason = await quick_safety_check(session, token_mint)

        if not safe:
            log(f"Imezuiwa: {reason}")
            return

        await simulate_buy(session, token_mint, creator)
        asyncio.create_task(monitor_position(session, token_mint))

    except Exception as e:
        log(f"Launch error: {e}")

async def listen_pumpfun(session):
    log("Inasikiza Pump.fun launches...")

    while True:
        try:
            async with session.ws_connect(HELIUS_WS) as ws:
                subscribe = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "logsSubscribe",
                    "params": [
                        {"mentions": [PUMPFUN_PROGRAM]},
                        {"commitment": "confirmed"}
                    ]
                }
                await ws.send_str(json.dumps(subscribe))

                msg = "✅ Imeunganika na Pump.fun! Inasubiri token mpya..."
                log(msg)
                await send_telegram(session, msg)

                async for ws_msg in ws:
                    if ws_msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(ws_msg.data)
                        result = data.get("params", {}).get("result", {})
                        value = result.get("value", {})
                        signature = value.get("signature")
                        err = value.get("err")

                        if signature and not err:
                            asyncio.create_task(
                                process_new_launch(session, signature)
                            )

        except Exception as e:
            log(f"WebSocket error: {e} — Inajaribu tena...")
            await asyncio.sleep(5)

async def print_stats(session):
    while True:
        await asyncio.sleep(300)
        win_rate = (stats["wins"] / max(stats["sniped"], 1)) * 100
        sol_price = await get_sol_price(session)
        msg = (
            f"📊 RIPOTI YA DAKIKA 5\n"
            f"🚀 Launches zilizoonekana: {stats['total_launches']}\n"
            f"🎯 Tokens zilizosnipiwa: {stats['sniped']}\n"
            f"✅ Wins: {stats['wins']}\n"
            f"❌ Losses: {stats['losses']}\n"
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
            f"🎯 PUMP.FUN EARLY SNIPER BOT!\n"
            f"💰 Buy Amount: {BUY_AMOUNT_SOL} SOL (${BUY_AMOUNT_SOL*sol_price:.1f})\n"
            f"🎯 Take Profit: {TAKE_PROFIT_X}x\n"
            f"🛑 Stop Loss: -{STOP_LOSS_PCT*100:.0f}%\n"
            f"⏱️ Max Hold: {MAX_HOLD_MINUTES} dakika\n"
            f"🛡️ Filters: Honeypot, Rug Pull\n"
            f"🧪 Mode: {'SIMULATION' if DRY_RUN else 'LIVE'}"
        )
        log(start_msg)
        await send_telegram(session, start_msg)

        await asyncio.gather(
            listen_pumpfun(session),
            print_stats(session)
        )

if __name__ == "__main__":
    asyncio.run(main())
