import asyncio
import aiohttp
import time
from datetime import datetime

TELEGRAM_TOKEN = "8778061073:AAF1hhp3hz-ZjgJwaMmfAozEgbpxK9yCsNo"
TELEGRAM_CHAT_ID = "7010983039"
HELIUS_RPC = "https://mainnet.helius-rpc.com/?api-key=04e4a6db-29bd-4b08-99d9-46ad23e9feb1"
HELIUS_KEY = "04e4a6db-29bd-4b08-99d9-46ad23e9feb1"
JUPITER_API = "https://quote-api.jup.ag/v6"

PUMPFUN_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
RAYDIUM_PROGRAM = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
SOL_MINT = "So11111111111111111111111111111111111111112"

DRY_RUN = True

BUY_AMOUNT_SOL = 0.05
TAKE_PROFIT_MIN = 0.10
TAKE_PROFIT_MAX = 0.20
TRAILING_STOP = 0.05
STOP_LOSS_PCT = 0.25
MAX_HOLD_MINUTES = 5
MIN_LIQUIDITY_USD = 3000
MAX_PRICE_IMPACT = 20

positions = {}
seen_tokens = set()
processed_sigs = set()

stats = {
    "found": 0,
    "bought": 0,
    "wins": 0,
    "losses": 0,
    "pnl_sol": 0.0
}

def log(msg):
    now = datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] {msg}")

async def send_telegram(session, msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        await session.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        })
    except Exception as e:
        log(f"Telegram error: {e}")

async def rpc_call(session, method, params):
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
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
            data = await r.json()
            return float(data["solana"]["usd"])
    except:
        return 85.0

async def get_token_price_sol(session, token_mint, amount=1000000):
    try:
        url = (
            f"{JUPITER_API}/quote?"
            f"inputMint={token_mint}"
            f"&outputMint={SOL_MINT}"
            f"&amount={amount}"
            f"&slippageBps=2500"
        )
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
            if r.status != 200:
                return 0, 0
            data = await r.json()
            out_amount = int(data.get("outAmount", 0))
            impact = float(data.get("priceImpactPct", 100))
            price_per_token = out_amount / 1e9 / amount
            return price_per_token, impact
    except:
        return 0, 100

async def can_buy_token(session, token_mint):
    try:
        buy_sol = int(BUY_AMOUNT_SOL * 1e9)
        url = (
            f"{JUPITER_API}/quote?"
            f"inputMint={SOL_MINT}"
            f"&outputMint={token_mint}"
            f"&amount={buy_sol}"
            f"&slippageBps=2500"
        )
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
            if r.status != 200:
                return False, 0
            data = await r.json()
            impact = float(data.get("priceImpactPct", 100))
            out_amount = int(data.get("outAmount", 0))
            return impact < MAX_PRICE_IMPACT, out_amount
    except:
        return False, 0

async def safety_check(session, token_mint):
    results = []

    can_buy, tokens_out = await can_buy_token(session, token_mint)
    if not can_buy:
        return False, "Haiwezi kununuliwa", 0

    price_sol, sell_impact = await get_token_price_sol(session, token_mint)
    if sell_impact > MAX_PRICE_IMPACT:
        return False, f"Honeypot — sell impact {sell_impact:.0f}%", 0

    sol_price = await get_sol_price(session)
    liquidity_usd = (BUY_AMOUNT_SOL * sol_price) * (100 / max(sell_impact, 0.1))
    if liquidity_usd < MIN_LIQUIDITY_USD:
        return False, f"Liquidity ndogo ${liquidity_usd:.0f}", 0

    try:
        result = await rpc_call(session, "getAccountInfo", [
            token_mint, {"encoding": "jsonParsed"}
        ])
        if result:
            parsed = result.get("value", {}).get("data", {}).get("parsed", {})
            mint_auth = parsed.get("info", {}).get("mintAuthority")
            freeze_auth = parsed.get("info", {}).get("freezeAuthority")
            if mint_auth:
                results.append("⚠️ Mint authority ipo")
            if freeze_auth:
                results.append("⚠️ Freeze authority ipo")
    except:
        pass

    return True, " | ".join(results) if results else "✅ Imepita checks", tokens_out

async def open_position(session, token_mint, creator, tokens_out):
    if token_mint in positions:
        return

    price_sol, _ = await get_token_price_sol(session, token_mint)
    sol_price = await get_sol_price(session)

    positions[token_mint] = {
        "mint": token_mint,
        "creator": creator,
        "entry_price_sol": price_sol,
        "tokens": tokens_out,
        "buy_sol": BUY_AMOUNT_SOL,
        "entry_time": time.time(),
        "peak_price_sol": price_sol,
        "sold": False,
        "tp_hit": False
    }

    stats["bought"] += 1
    pump_url = f"https://pump.fun/{token_mint}"

    msg = (
        f"🚀 INANUNUA TOKEN MPYA!\n"
        f"🪙 <a href='{pump_url}'>{token_mint[:16]}...</a>\n"
        f"👤 Creator: {creator[:8]}...\n"
        f"💰 Kununua: {BUY_AMOUNT_SOL} SOL (${BUY_AMOUNT_SOL*sol_price:.2f})\n"
        f"📦 Tokens: {tokens_out:,}\n"
        f"🎯 TP: +{TAKE_PROFIT_MIN*100:.0f}% ~ +{TAKE_PROFIT_MAX*100:.0f}%\n"
        f"🛑 SL: -{STOP_LOSS_PCT*100:.0f}%\n"
        f"⏱️ Max: {MAX_HOLD_MINUTES} dakika\n"
        f"🧪 SIMULATION"
    )
    log(f"Inanunua: {token_mint[:8]}...")
    await send_telegram(session, msg)

    asyncio.create_task(monitor_position(session, token_mint))

async def monitor_position(session, token_mint):
    await asyncio.sleep(10)

    if token_mint not in positions:
        return

    pos = positions[token_mint]
    entry = pos["entry_price_sol"]

    if entry <= 0:
        pos["sold"] = True
        return

    sol_price = await get_sol_price(session)

    while not pos["sold"]:
        try:
            current_price, impact = await get_token_price_sol(session, token_mint)
            elapsed_min = (time.time() - pos["entry_time"]) / 60

            if current_price <= 0:
                await asyncio.sleep(10)
                continue

            change = (current_price - entry) / entry
            pnl_sol = pos["buy_sol"] * change
            pnl_usd = pnl_sol * sol_price

            if current_price > pos["peak_price_sol"]:
                pos["peak_price_sol"] = current_price

            peak_change = (pos["peak_price_sol"] - entry) / entry
            drop_from_peak = (pos["peak_price_sol"] - current_price) / pos["peak_price_sol"] if pos["peak_price_sol"] > 0 else 0

            reason = None

            if change >= TAKE_PROFIT_MIN and not pos["tp_hit"]:
                pos["tp_hit"] = True
                log(f"✅ {token_mint[:8]}... imepanda {change*100:.1f}% — trailing stop imeanza!")

            if pos["tp_hit"] and drop_from_peak >= TRAILING_STOP:
                reason = "TRAILING_STOP"

            elif change >= TAKE_PROFIT_MAX:
                reason = "TAKE_PROFIT"

            elif change <= -STOP_LOSS_PCT:
                reason = "STOP_LOSS"

            elif elapsed_min >= MAX_HOLD_MINUTES:
                reason = "TIME"

            if reason:
                pos["sold"] = True

                if pnl_sol > 0:
                    stats["wins"] += 1
                    emoji = "💰"
                else:
                    stats["losses"] += 1
                    emoji = "🛑"

                stats["pnl_sol"] += pnl_sol
                win_rate = (stats["wins"] / max(stats["bought"], 1)) * 100

                reason_text = {
                    "TAKE_PROFIT": "TAKE PROFIT! 🎯",
                    "TRAILING_STOP": "TRAILING STOP 📉",
                    "STOP_LOSS": "STOP LOSS ❌",
                    "TIME": "MUDA UMEISHA ⏱️"
                }.get(reason, reason)

                msg = (
                    f"{emoji} {reason_text}\n"
                    f"🪙 {token_mint[:8]}...\n"
                    f"📈 Mabadiliko: {change*100:+.1f}%\n"
                    f"📊 Peak: +{peak_change*100:.1f}%\n"
                    f"⏱️ Hold: {elapsed_min:.1f} dakika\n"
                    f"━━━━━━━━━━━\n"
                    f"💵 PnL: {pnl_sol:+.4f} SOL (${pnl_usd:+.2f})\n"
                    f"📊 Total PnL: {stats['pnl_sol']:.4f} SOL\n"
                    f"🏆 Win Rate: {win_rate:.1f}%\n"
                    f"✅ {stats['wins']} Wins | ❌ {stats['losses']} Losses\n"
                    f"🧪 SIMULATION"
                )
                log(msg)
                await send_telegram(session, msg)
                break

            await asyncio.sleep(15)

        except Exception as e:
            log(f"Monitor error: {e}")
            await asyncio.sleep(15)

async def parse_new_tokens(session, signature):
    try:
        result = await rpc_call(session, "getTransaction", [
            signature,
            {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}
        ])
        if not result:
            return []

        meta = result.get("meta", {})
        if meta.get("err"):
            return []

        pre_mints = {b["mint"] for b in meta.get("preTokenBalances", [])}
        post_balances = meta.get("postTokenBalances", [])

        accounts = result.get("transaction", {}).get("message", {}).get("accountKeys", [])
        creator = None
        for acc in accounts:
            if isinstance(acc, dict) and acc.get("signer"):
                pubkey = acc.get("pubkey", "")
                if pubkey not in [PUMPFUN_PROGRAM, RAYDIUM_PROGRAM]:
                    creator = pubkey
                    break

        new_tokens = []
        for b in post_balances:
            mint = b.get("mint", "")
            if mint and mint not in pre_mints and mint != SOL_MINT and mint not in seen_tokens:
                seen_tokens.add(mint)
                new_tokens.append({"mint": mint, "creator": creator})

        return new_tokens
    except:
        return []

async def poll_new_pairs(session):
    log("Inaangalia new pairs kwenye Solana...")
    await send_telegram(session, "🔍 Bot inaanza kutafuta new pairs...")

    last_sig = None

    while True:
        try:
            params = [PUMPFUN_PROGRAM, {"limit": 10, "commitment": "confirmed"}]
            if last_sig:
                params[1]["until"] = last_sig

            sigs = await rpc_call(session, "getSignaturesForAddress", params)

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
                if not s.get("err"):
                    new_sigs.append(s["signature"])

            if new_sigs:
                last_sig = sigs[0]["signature"]

                for sig in new_sigs[:3]:
                    if sig in processed_sigs:
                        continue
                    processed_sigs.add(sig)

                    tokens = await parse_new_tokens(session, sig)
                    for t in tokens:
                        stats["found"] += 1
                        mint = t["mint"]
                        creator = t["creator"] or "Unknown"

                        log(f"🆕 Token mpya: {mint[:8]}... — Inachunguza...")

                        safe, reason, tokens_out = await safety_check(session, mint)

                        if not safe:
                            log(f"❌ Imezuiwa: {reason}")
                            await send_telegram(session, f"❌ Token imezuiwa\n🪙 {mint[:8]}...\n⚠️ {reason}")
                        else:
                            await open_position(session, mint, creator, tokens_out)

            await asyncio.sleep(2)

        except Exception as e:
            log(f"Poll error: {e}")
            await asyncio.sleep(5)

async def print_stats(session):
    while True:
        await asyncio.sleep(300)
        sol_price = await get_sol_price(session)
        win_rate = (stats["wins"] / max(stats["bought"], 1)) * 100
        msg = (
            f"📊 RIPOTI YA DAKIKA 5\n"
            f"🔍 Tokens zilizoonekana: {stats['found']}\n"
            f"🛒 Zilizobought: {stats['bought']}\n"
            f"✅ Wins: {stats['wins']} | ❌ Losses: {stats['losses']}\n"
            f"🏆 Win Rate: {win_rate:.1f}%\n"
            f"💰 Total PnL: {stats['pnl_sol']:.4f} SOL\n"
            f"💵 USD: ${stats['pnl_sol']*sol_price:.2f}\n"
            f"🧪 SIMULATION"
        )
        log(msg)
        await send_telegram(session, msg)

async def main():
    async with aiohttp.ClientSession() as session:
        sol_price = await get_sol_price(session)
        start_msg = (
            f"🎯 SOLANA NEW PAIR SNIPER!\n"
            f"📡 Platform: Pump.fun (Onchain)\n"
            f"💰 Buy: {BUY_AMOUNT_SOL} SOL (${BUY_AMOUNT_SOL*sol_price:.2f})\n"
            f"🎯 TP: +{TAKE_PROFIT_MIN*100:.0f}% ~ +{TAKE_PROFIT_MAX*100:.0f}%\n"
            f"📉 Trailing Stop: -{TRAILING_STOP*100:.0f}% kutoka peak\n"
            f"🛑 SL: -{STOP_LOSS_PCT*100:.0f}%\n"
            f"⏱️ Max Hold: {MAX_HOLD_MINUTES} dakika\n"
            f"🛡️ Filters: Honeypot, Low Liquidity\n"
            f"🧪 SIMULATION"
        )
        log(start_msg)
        await send_telegram(session, start_msg)

        await asyncio.gather(
            poll_new_pairs(session),
            print_stats(session)
        )

if __name__ == "__main__":
    asyncio.run(main())
