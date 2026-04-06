import asyncio
import aiohttp
import time
from datetime import datetime

TELEGRAM_TOKEN = "8778061073:AAFvbdcKusf3P74VLTzdcYa7obV2LrgDXyE"
TELEGRAM_CHAT_ID = "7010983039"
HELIUS_RPC = "https://mainnet.helius-rpc.com/?api-key=04e4a6db-29bd-4b08-99d9-46ad23e9feb1"
HELIUS_API = "https://api.helius.xyz/v0"
HELIUS_KEY = "04e4a6db-29bd-4b08-99d9-46ad23e9feb1"
JUPITER_API = "https://quote-api.jup.ag/v6"

DRY_RUN = True

WHALE_WALLETS = [
    "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
    "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM",
    "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh",
    "CuieVDEDtLo7FypA9SbLM9saXFdb1dsshEkyErMqkRQq",
]

MIN_WHALE_BUY_USD = 5000
MIN_LIQUIDITY_USD = 20000
MAX_TOP_HOLDER_PCT = 20
MIN_WALLET_AGE_DAYS = 30
MIN_WHALE_WIN_RATE = 0.55
MAX_PRICE_IMPACT_PCT = 10
BUY_AMOUNT_SOL = 0.05

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
        return 130.0

async def get_token_price_usd(session, token_mint):
    try:
        url = f"https://price.jup.ag/v4/price?ids={token_mint}"
        async with session.get(url) as r:
            data = await r.json()
            price = data.get("data", {}).get(token_mint, {}).get("price", 0)
            return float(price)
    except:
        return 0.0

async def check_liquidity(session, token_mint):
    try:
        url = f"{JUPITER_API}/quote?inputMint=So11111111111111111111111111111111111111112&outputMint={token_mint}&amount=1000000000&slippageBps=1000"
        async with session.get(url) as r:
            if r.status != 200:
                return 0
            data = await r.json()
            impact = float(data.get("priceImpactPct", 100))
            if impact > MAX_PRICE_IMPACT_PCT:
                return 0
            sol_price = await get_sol_price(session)
            return 1 * sol_price * (100 / max(impact, 0.01))
    except:
        return 0

async def can_sell_token(session, token_mint):
    try:
        url = f"{JUPITER_API}/quote?inputMint={token_mint}&outputMint=So11111111111111111111111111111111111111112&amount=1000000&slippageBps=1000"
        async with session.get(url) as r:
            if r.status != 200:
                return False
            data = await r.json()
            impact = float(data.get("priceImpactPct", 100))
            return impact < MAX_PRICE_IMPACT_PCT
    except:
        return False

async def check_mint_authority(session, token_mint):
    try:
        result = await helius_rpc(session, "getAccountInfo", [
            token_mint,
            {"encoding": "jsonParsed"}
        ])
        if not result:
            return True
        info = result.get("value", {})
        if not info:
            return True
        parsed = info.get("data", {}).get("parsed", {})
        mint_auth = parsed.get("info", {}).get("mintAuthority")
        freeze_auth = parsed.get("info", {}).get("freezeAuthority")
        return bool(mint_auth or freeze_auth)
    except:
        return True

async def check_top_holders(session, token_mint):
    try:
        url = f"{HELIUS_API}/token-holders?api-key={HELIUS_KEY}&mint={token_mint}&limit=10"
        async with session.get(url) as r:
            if r.status != 200:
                return True
            data = await r.json()
            holders = data.get("result", [])
            if not holders:
                return True
            total = sum(h.get("amount", 0) for h in holders)
            if total == 0:
                return True
            top_holder = max(h.get("amount", 0) for h in holders)
            top_pct = (top_holder / total) * 100
            return top_pct > MAX_TOP_HOLDER_PCT
    except:
        return True

async def get_wallet_age_days(session, wallet):
    try:
        result = await helius_rpc(session, "getSignaturesForAddress", [wallet, {"limit": 1000}])
        if not result:
            return 0
        oldest = result[-1].get("blockTime", int(time.time()))
        return (int(time.time()) - oldest) / 86400
    except:
        return 0

async def get_whale_win_rate(session, wallet):
    try:
        url = f"{HELIUS_API}/addresses/{wallet}/transactions?api-key={HELIUS_KEY}&limit=50&type=SWAP"
        async with session.get(url) as r:
            if r.status != 200:
                return 0
            txs = await r.json()
            if not txs or len(txs) < 5:
                return 0
            wins = 0
            total = 0
            for tx in txs[:20]:
                swap = tx.get("events", {}).get("swap", {})
                if swap:
                    total += 1
                    amount_out = swap.get("nativeOutput", {}).get("amount", 0)
                    amount_in = swap.get("nativeInput", {}).get("amount", 0)
                    if amount_out > amount_in:
                        wins += 1
            return wins / total if total > 0 else 0
    except:
        return 0

async def score_whale(session, wallet):
    score = 0
    reasons = []

    age_days = await get_wallet_age_days(session, wallet)
    if age_days < MIN_WALLET_AGE_DAYS:
        return 0, [f"Wallet changa sana: siku {age_days:.0f}"]
    score += 30 if age_days > 180 else 15
    reasons.append(f"Umri wa wallet: siku {age_days:.0f}")

    win_rate = await get_whale_win_rate(session, wallet)
    if win_rate < MIN_WHALE_WIN_RATE:
        return 0, [f"Win rate mbaya: {win_rate*100:.0f}%"]
    score += 40 if win_rate > 0.7 else 20
    reasons.append(f"Win rate: {win_rate*100:.0f}%")

    balance = await helius_rpc(session, "getBalance", [wallet])
    if balance:
        sol_balance = balance / 1e9
        if sol_balance < 100:
            return 0, [f"Balance ndogo: {sol_balance:.0f} SOL"]
        score += 30 if sol_balance > 1000 else 15
        reasons.append(f"Balance: {sol_balance:.0f} SOL")

    return score, reasons

async def safety_check(session, token_mint):
    checks = {"passed": 0, "total": 5, "reasons": []}

    dangerous_mint = await check_mint_authority(session, token_mint)
    if not dangerous_mint:
        checks["passed"] += 1
        checks["reasons"].append("✅ Mint authority imefungwa")
    else:
        checks["reasons"].append("❌ Mint authority ipo")

    can_sell = await can_sell_token(session, token_mint)
    if can_sell:
        checks["passed"] += 1
        checks["reasons"].append("✅ Token inaweza kuuzwa")
    else:
        checks["reasons"].append("❌ Honeypot — haiwezi kuuzwa!")

    liquidity = await check_liquidity(session, token_mint)
    if liquidity >= MIN_LIQUIDITY_USD:
        checks["passed"] += 1
        checks["reasons"].append(f"✅ Liquidity: ${liquidity:.0f}")
    else:
        checks["reasons"].append(f"❌ Liquidity ndogo: ${liquidity:.0f}")

    bad_holders = await check_top_holders(session, token_mint)
    if not bad_holders:
        checks["passed"] += 1
        checks["reasons"].append("✅ Holders wamegawanyika vizuri")
    else:
        checks["reasons"].append("❌ Holder mmoja ana zaidi ya 20%")

    price = await get_token_price_usd(session, token_mint)
    if price > 0:
        checks["passed"] += 1
        checks["reasons"].append(f"✅ Bei: ${price:.8f}")
    else:
        checks["reasons"].append("❌ Bei haipatikani")

    checks["safe"] = checks["passed"] >= 4
    return checks

async def analyze_whale_transaction(session, wallet, signature):
    try:
        result = await helius_rpc(session, "getTransaction", [
            signature,
            {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}
        ])
        if not result:
            return None

        meta = result.get("meta", {})
        if meta.get("err"):
            return None

        pre_balances = meta.get("preTokenBalances", [])
        post_balances = meta.get("postTokenBalances", [])

        if not post_balances:
            return None

        bought_tokens = []
        pre_mints = {b["mint"]: b.get("uiTokenAmount", {}).get("uiAmount", 0)
                     for b in pre_balances if b.get("owner") == wallet}
        post_mints = {b["mint"]: b.get("uiTokenAmount", {}).get("uiAmount", 0)
                      for b in post_balances if b.get("owner") == wallet}

        for mint, post_amount in post_mints.items():
            pre_amount = pre_mints.get(mint, 0)
            if post_amount > (pre_amount or 0):
                sol_price = await get_sol_price(session)
                pre_sol = meta.get("preBalances", [0])[0] / 1e9
                post_sol = meta.get("postBalances", [0])[0] / 1e9
                sol_spent = pre_sol - post_sol
                usd_spent = sol_spent * sol_price
                if usd_spent >= MIN_WHALE_BUY_USD:
                    bought_tokens.append({
                        "mint": mint,
                        "sol_spent": sol_spent,
                        "usd_spent": usd_spent,
                        "amount_received": post_amount - (pre_amount or 0)
                    })

        return bought_tokens if bought_tokens else None

    except Exception as e:
        log(f"Analyze error: {e}")
        return None

async def process_opportunity(session, whale_wallet, token_info):
    mint = token_info["mint"]
    log(f"Whale amenunua token: {mint[:8]}...")

    alert_msg = (
        f"🎯 WHALE AMENUNUA TOKEN!\n"
        f"👛 Whale: {whale_wallet[:8]}...\n"
        f"🪙 Token: {mint[:8]}...\n"
        f"💰 Ametumia: ${token_info['usd_spent']:.0f}\n"
        f"🔍 Inachunguza usalama..."
    )
    await send_telegram(session, alert_msg)

    whale_score, whale_reasons = await score_whale(session, whale_wallet)
    if whale_score < 60:
        msg = (
            f"❌ WHALE HAINA UBORA\n"
            f"🪙 Token: {mint[:8]}...\n"
            f"📊 Score: {whale_score}/100\n"
            f"📝 {', '.join(whale_reasons)}"
        )
        await send_telegram(session, msg)
        return

    safety = await safety_check(session, mint)
    safety_report = "\n".join(safety["reasons"])
    await send_telegram(session, f"🔐 UCHUNGUZI WA TOKEN\n🪙 {mint[:8]}...\n{safety_report}")

    if not safety["safe"]:
        msg = (
            f"🚫 TOKEN IMEZUIWA!\n"
            f"🪙 Token: {mint[:8]}...\n"
            f"⚠️ Rug pull / Honeypot / Scam!"
        )
        await send_telegram(session, msg)
        return

    mode = "🧪 SIMULATION" if DRY_RUN else "🔴 LIVE"
    msg = (
        f"✅ TOKEN SALAMA — INANUNUA!\n"
        f"🪙 Token: {mint[:8]}...\n"
        f"💰 Whale alitumia: ${token_info['usd_spent']:.0f}\n"
        f"📊 Whale Score: {whale_score}/100\n"
        f"💸 Kununua: {BUY_AMOUNT_SOL} SOL\n"
        f"{mode}"
    )
    await send_telegram(session, msg)

async def watch_whale(session, wallet):
    log(f"Inaangalia whale: {wallet[:8]}...")
    last_sig = None

    while True:
        try:
            sigs = await helius_rpc(session, "getSignaturesForAddress", [wallet, {"limit": 5}])
            if not sigs:
                await asyncio.sleep(5)
                continue

            latest_sig = sigs[0]["signature"]
            if last_sig is None:
                last_sig = latest_sig
                await asyncio.sleep(5)
                continue

            if latest_sig == last_sig:
                await asyncio.sleep(5)
                continue

            new_sigs = []
            for s in sigs:
                if s["signature"] == last_sig:
                    break
                new_sigs.append(s["signature"])

            last_sig = latest_sig

            for sig in new_sigs:
                bought = await analyze_whale_transaction(session, wallet, sig)
                if bought:
                    for token_info in bought:
                        await process_opportunity(session, wallet, token_info)

            await asyncio.sleep(3)

        except Exception as e:
            log(f"Watch error: {e}")
            await asyncio.sleep(10)

async def main():
    async with aiohttp.ClientSession() as session:
        start_msg = (
            f"🤖 SOLANA WHALE SNIPER BOT!\n"
            f"🔍 Whales zinazofuatiliwa: {len(WHALE_WALLETS)}\n"
            f"🛡️ Filters: Honeypot, Rug Pull, Scam, Fake Whale\n"
            f"💰 Min Whale Buy: ${MIN_WHALE_BUY_USD}\n"
            f"💧 Min Liquidity: ${MIN_LIQUIDITY_USD}\n"
            f"🧪 Mode: {'SIMULATION' if DRY_RUN else 'LIVE'}"
        )
        log(start_msg)
        await send_telegram(session, start_msg)
        tasks = [watch_whale(session, wallet) for wallet in WHALE_WALLETS]
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
