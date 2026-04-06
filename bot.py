import asyncio
import aiohttp
import json
import time
from datetime import datetime

TELEGRAM_TOKEN = "8778061073:AAFvbdcKusf3P74VLTzdcYa7obV2LrgDXyE"
TELEGRAM_CHAT_ID = "7010983039"
HELIUS_RPC = "https://mainnet.helius-rpc.com/?api-key=04e4a6db-29bd-4b08-99d9-46ad23e9feb1"
HELIUS_WS = "wss://mainnet.helius-rpc.com/?api-key=04e4a6db-29bd-4b08-99d9-46ad23e9feb1"
HELIUS_API = "https://api.helius.xyz/v0"
HELIUS_KEY = "04e4a6db-29bd-4b08-99d9-46ad23e9feb1"
JUPITER_API = "https://quote-api.jup.ag/v6"

PUMPFUN_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
SOL_MINT = "So11111111111111111111111111111111111111112"

DRY_RUN = True

MIN_WHALE_BUY_SOL = 10
MIN_WHALE_WIN_RATE = 0.55
MIN_WALLET_AGE_DAYS = 7
MIN_LIQUIDITY_USD = 5000
MAX_PRICE_IMPACT_PCT = 15
BUY_AMOUNT_SOL = 0.05

discovered_whales = {}
blacklisted_wallets = set()
processed_tokens = set()

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

async def get_wallet_stats(session, wallet):
    try:
        url = f"{HELIUS_API}/addresses/{wallet}/transactions?api-key={HELIUS_KEY}&limit=50&type=SWAP"
        async with session.get(url) as r:
            if r.status != 200:
                return None
            txs = await r.json()
            if not txs or len(txs) < 3:
                return None

            wins = 0
            total = 0
            total_volume_sol = 0

            for tx in txs[:30]:
                swap = tx.get("events", {}).get("swap", {})
                if swap:
                    total += 1
                    amount_in = swap.get("nativeInput", {}).get("amount", 0)
                    amount_out = swap.get("nativeOutput", {}).get("amount", 0)
                    total_volume_sol += amount_in / 1e9
                    if amount_out > amount_in:
                        wins += 1

            win_rate = wins / total if total > 0 else 0
            avg_volume = total_volume_sol / total if total > 0 else 0

            return {
                "win_rate": win_rate,
                "total_trades": total,
                "avg_volume_sol": avg_volume,
                "total_volume_sol": total_volume_sol
            }
    except:
        return None

async def get_wallet_age_days(session, wallet):
    try:
        result = await helius_rpc(session, "getSignaturesForAddress", [
            wallet, {"limit": 1000}
        ])
        if not result:
            return 0
        oldest = result[-1].get("blockTime", int(time.time()))
        return (int(time.time()) - oldest) / 86400
    except:
        return 0

async def is_whale(session, wallet, sol_spent):
    if wallet in blacklisted_wallets:
        return False, "Blacklisted"

    if sol_spent < MIN_WHALE_BUY_SOL:
        return False, f"Ununuzi mdogo: {sol_spent:.1f} SOL"

    balance = await helius_rpc(session, "getBalance", [wallet])
    if not balance or balance / 1e9 < 50:
        blacklisted_wallets.add(wallet)
        return False, "Balance ndogo"

    age_days = await get_wallet_age_days(session, wallet)
    if age_days < MIN_WALLET_AGE_DAYS:
        blacklisted_wallets.add(wallet)
        return False, f"Wallet changa: siku {age_days:.0f}"

    stats = await get_wallet_stats(session, wallet)
    if not stats or stats["win_rate"] < MIN_WHALE_WIN_RATE:
        win_rate = stats["win_rate"] if stats else 0
        return False, f"Win rate mbaya: {win_rate*100:.0f}%"

    return True, f"Win rate: {stats['win_rate']*100:.0f}% | Trades: {stats['total_trades']}"

async def can_sell_token(session, token_mint):
    try:
        url = f"{JUPITER_API}/quote?inputMint={token_mint}&outputMint={SOL_MINT}&amount=1000000&slippageBps=1500"
        async with session.get(url) as r:
            if r.status != 200:
                return False
            data = await r.json()
            impact = float(data.get("priceImpactPct", 100))
            return impact < MAX_PRICE_IMPACT_PCT
    except:
        return False

async def check_liquidity(session, token_mint):
    try:
        url = f"{JUPITER_API}/quote?inputMint={SOL_MINT}&outputMint={token_mint}&amount=1000000000&slippageBps=1500"
        async with session.get(url) as r:
            if r.status != 200:
                return 0
            data = await r.json()
            impact = float(data.get("priceImpactPct", 100))
            if impact > MAX_PRICE_IMPACT_PCT:
                return 0
            sol_price = await get_sol_price(session)
            return sol_price * (100 / max(impact, 0.01))
    except:
        return 0

async def check_mint_authority(session, token_mint):
    try:
        result = await helius_rpc(session, "getAccountInfo", [
            token_mint, {"encoding": "jsonParsed"}
        ])
        if not result:
            return True
        parsed = result.get("value", {}).get("data", {}).get("parsed", {})
        mint_auth = parsed.get("info", {}).get("mintAuthority")
        freeze_auth = parsed.get("info", {}).get("freezeAuthority")
        return bool(mint_auth or freeze_auth)
    except:
        return True

async def safety_check(session, token_mint):
    checks = {"passed": 0, "total": 4, "reasons": []}

    if not await check_mint_authority(session, token_mint):
        checks["passed"] += 1
        checks["reasons"].append("✅ Mint authority imefungwa")
    else:
        checks["reasons"].append("❌ Mint authority ipo")

    if await can_sell_token(session, token_mint):
        checks["passed"] += 1
        checks["reasons"].append("✅ Token inaweza kuuzwa")
    else:
        checks["reasons"].append("❌ Honeypot!")

    liquidity = await check_liquidity(session, token_mint)
    if liquidity >= MIN_LIQUIDITY_USD:
        checks["passed"] += 1
        checks["reasons"].append(f"✅ Liquidity: ${liquidity:.0f}")
    else:
        checks["reasons"].append(f"❌ Liquidity ndogo: ${liquidity:.0f}")

    try:
        async with session.get(f"https://price.jup.ag/v4/price?ids={token_mint}") as r:
            data = await r.json()
            price = float(data.get("data", {}).get(token_mint, {}).get("price", 0))
            if price > 0:
                checks["passed"] += 1
                checks["reasons"].append(f"✅ Bei: ${price:.8f}")
            else:
                checks["reasons"].append("❌ Bei haipatikani")
    except:
        checks["reasons"].append("❌ Bei haipatikani")

    checks["safe"] = checks["passed"] >= 3
    return checks

async def process_pumpfun_transaction(session, signature):
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

        accounts = result.get("transaction", {}).get("message", {}).get("accountKeys", [])
        if not accounts:
            return

        buyer_wallet = None
        for acc in accounts:
            pubkey = acc.get("pubkey", "") if isinstance(acc, dict) else str(acc)
            if pubkey != PUMPFUN_PROGRAM and pubkey != SOL_MINT:
                buyer_wallet = pubkey
                break

        if not buyer_wallet:
            return

        pre_sol = meta.get("preBalances", [0])[0] / 1e9
        post_sol = meta.get("postBalances", [0])[0] / 1e9
        sol_spent = abs(pre_sol - post_sol)

        post_balances = meta.get("postTokenBalances", [])
        pre_balances = meta.get("preTokenBalances", [])

        pre_mints = {b["mint"] for b in pre_balances}
        new_tokens = [b["mint"] for b in post_balances if b["mint"] not in pre_mints]

        if not new_tokens:
            return

        token_mint = new_tokens[0]

        if token_mint in processed_tokens:
            return

        log(f"Pump.fun activity: {buyer_wallet[:8]}... alinunua {token_mint[:8]}... ({sol_spent:.2f} SOL)")

        whale_ok, whale_reason = await is_whale(session, buyer_wallet, sol_spent)

        if not whale_ok:
            log(f"Si whale: {whale_reason}")
            return

        if buyer_wallet not in discovered_whales:
            discovered_whales[buyer_wallet] = {
                "first_seen": datetime.now().strftime("%H:%M:%S"),
                "trades": 0
            }
            sol_price = await get_sol_price(session)
            msg = (
                f"🐋 WHALE MPYA IMEGUNDULIWA!\n"
                f"👛 Wallet: {buyer_wallet[:8]}...\n"
                f"📊 {whale_reason}\n"
                f"💰 Ununuzi wa kwanza: {sol_spent:.2f} SOL (${sol_spent*sol_price:.0f})\n"
                f"🪙 Token: {token_mint[:8]}...\n"
                f"🔍 Inachunguza token..."
            )
            await send_telegram(session, msg)

        discovered_whales[buyer_wallet]["trades"] += 1
        processed_tokens.add(token_mint)

        safety = await safety_check(session, token_mint)
        safety_report = "\n".join(safety["reasons"])

        if not safety["safe"]:
            msg = (
                f"🚫 TOKEN IMEZUIWA!\n"
                f"🪙 {token_mint[:8]}...\n"
                f"⚠️ Hatari imegunduliwa!\n"
                f"{safety_report}"
            )
            await send_telegram(session, msg)
            return

        sol_price = await get_sol_price(session)
        mode = "🧪 SIMULATION" if DRY_RUN else "🔴 LIVE"
        msg = (
            f"✅ FURSA IMEPATIKANA!\n"
            f"🐋 Whale: {buyer_wallet[:8]}...\n"
            f"🪙 Token: {token_mint[:8]}...\n"
            f"💰 Whale alitumia: {sol_spent:.2f} SOL (${sol_spent*sol_price:.0f})\n"
            f"📊 {whale_reason}\n"
            f"{safety_report}\n"
            f"💸 Kununua: {BUY_AMOUNT_SOL} SOL\n"
            f"{mode}"
        )
        await send_telegram(session, msg)

    except Exception as e:
        log(f"Process error: {e}")

async def listen_pumpfun(session):
    log("Inasikiza Pump.fun transactions...")

    while True:
        try:
            async with session.ws_connect(HELIUS_WS) as ws:
                subscribe_msg = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "logsSubscribe",
                    "params": [
                        {"mentions": [PUMPFUN_PROGRAM]},
                        {"commitment": "confirmed"}
                    ]
                }
                await ws.send_str(json.dumps(subscribe_msg))
                log("✅ Imeunganika na Pump.fun!")

                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        result = data.get("params", {}).get("result", {})
                        logs_result = result.get("value", {})
                        signature = logs_result.get("signature")

                        if signature and "err" not in str(logs_result.get("err", "")):
                            asyncio.create_task(
                                process_pumpfun_transaction(session, signature)
                            )

        except Exception as e:
            log(f"WebSocket error: {e} — Inajaribu tena...")
            await asyncio.sleep(5)

async def print_stats(session):
    while True:
        await asyncio.sleep(300)
        msg = (
            f"📊 RIPOTI YA KILA DAKIKA 5\n"
            f"🐋 Whales zilizogundulika: {len(discovered_whales)}\n"
            f"🪙 Tokens zilizochunguzwa: {len(processed_tokens)}\n"
            f"🚫 Wallets blacklisted: {len(blacklisted_wallets)}\n"
            f"🧪 Mode: {'SIMULATION' if DRY_RUN else 'LIVE'}"
        )
        log(msg)
        await send_telegram(session, msg)

async def main():
    async with aiohttp.ClientSession() as session:
        start_msg = (
            f"🤖 PUMP.FUN AUTONOMOUS WHALE SNIPER!\n"
            f"🔍 Inatafuta whales yenyewe\n"
            f"🎯 Platform: Pump.fun (Solana)\n"
            f"💰 Min Whale Buy: {MIN_WHALE_BUY_SOL} SOL\n"
            f"📊 Min Win Rate: {MIN_WHALE_WIN_RATE*100:.0f}%\n"
            f"🛡️ Filters: Honeypot, Rug Pull, Scam\n"
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
