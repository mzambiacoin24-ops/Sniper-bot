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
    "AVAZvHLR2PcWpDf8BXY4rVxNHYRBytycHkcB5z5QNXYm",
    "4Be9CvxqHW6BYiRAxW9Q3xu1ycTMWaL5z8NX4HR3ha7t",
    "8zFZHuSRuDpuAR7J6FzwyF3vKNx4CVW3DFHJerQhc7Zd",
    "H72yLkhTnoBfhBTXXaj1RBXuirm8s8G5fcVh2XpQLggM",
    "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
    "CuieVDEDtLo7FypA9SbLM9saXFdb1dsshEkyErMqkRQq",
]

MIN_WHALE_BUY_USD = 1000
MIN_LIQUIDITY_USD = 10000
MAX_TOP_HOLDER_PCT = 20
MIN_WALLET_AGE_DAYS = 7
MAX_PRICE_IMPACT_PCT = 15
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
        return 85.0

async def can_sell_token(session, token_mint):
    try:
        url = f"{JUPITER_API}/quote?inputMint={token_mint}&outputMint=So11111111111111111111111111111111111111112&amount=1000000&slippageBps=1500"
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
        url = f"{JUPITER_API}/quote?inputMint=So11111111111111111111111111111111111111112&outputMint={token_mint}&amount=1000000000&slippageBps=1500"
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

async def check_mint_authority(session, token_mint):
    try:
        result = await helius_rpc(session, "getAccountInfo", [
            token_mint, {"encoding": "jsonParsed"}
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

async def safety_check(session, token_mint):
    checks = {"passed": 0, "total": 4, "reasons": []}

    dangerous_mint = await check_mint_authority(session, token_mint)
    if not dangerous_mint:
        checks["passed"] += 1
        checks["reasons"].append("✅ Mint authority imefungwa")
    else:
        checks["reasons"].append("❌ Mint authority ipo — hatari!")

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

    price_url = f"https://price.jup.ag/v4/price?ids={token_mint}"
    try:
        async with session.get(price_url) as r:
            data = await r.json()
            price = data.get("data", {}).get(token_mint, {}).get("price", 0)
            if float(price) > 0:
                checks["passed"] += 1
                checks["reasons"].append(f"✅ Bei: ${float(price):.8f}")
            else:
                checks["reasons"].append("❌ Bei haipatikani")
    except:
        checks["reasons"].append("❌ Bei haipatikani")

    checks["safe"] = checks["passed"] >= 3
    return checks

async def analyze_transaction(session, wallet, signature):
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
                sol_spent = abs(pre_sol - post_sol)
                usd_spent = sol_spent * sol_price
                if usd_spent >= MIN_WHALE_BUY_USD:
                    bought_tokens.append({
                        "mint": mint,
                        "sol_spent": sol_spent,
                        "usd_spent": usd_spent,
                    })

        return bought_tokens if bought_tokens else None

    except Exception as e:
        log(f"Analyze error: {e}")
        return None

async def process_opportunity(session, whale_wallet, token_info):
    mint = token_info["mint"]
    log(f"Whale amenunua: {mint[:8]}...")

    alert_msg = (
        f"🎯 WHALE AMENUNUA TOKEN!\n"
        f"👛 Whale: {whale_wallet[:8]}...\n"
        f"🪙 Token: {mint[:8]}...\n"
        f"💰 Ametumia: ${token_info['usd_spent']:.0f}\n"
        f"🔍 Inachunguza usalama..."
    )
    await send_telegram(session, alert_msg)

    safety = await safety_check(session, mint)
    safety_report = "\n".join(safety["reasons"])
    await send_telegram(session, f"🔐 UCHUNGUZI:\n🪙 {mint[:8]}...\n{safety_report}")

    if not safety["safe"]:
        msg = (
            f"🚫 TOKEN IMEZUIWA!\n"
            f"🪙 {mint[:8]}...\n"
            f"⚠️ Rug pull / Honeypot / Scam!"
        )
        await send_telegram(session, msg)
        return

    mode = "🧪 SIMULATION" if DRY_RUN else "🔴 LIVE"
    msg = (
        f"✅ TOKEN SALAMA!\n"
        f"🪙 Token: {mint[:8]}...\n"
        f"💰 Whale alitumia: ${token_info['usd_spent']:.0f}\n"
        f"💸 Kununua: {BUY_AMOUNT_SOL} SOL\n"
        f"{mode}"
    )
    await send_telegram(session, msg)

async def watch_whale(session, wallet):
    log(f"Inaangalia whale: {wallet[:8]}...")
    last_sig = None

    while True:
        try:
            sigs = await helius_rpc(session, "getSignaturesForAddress", [
                wallet, {"limit": 5}
            ])
            if not sigs:
                await asyncio.sleep(5)
                continue

            latest_sig = sigs[0]["signature"]
            if last_sig is None:
                last_sig = latest_sig
                await asyncio.sleep(3)
                continue

            if latest_sig == last_sig:
                await asyncio.sleep(3)
                continue

            new_sigs = []
            for s in sigs:
                if s["signature"] == last_sig:
                    break
                new_sigs.append(s["signature"])

            last_sig = latest_sig

            for sig in new_sigs:
                bought = await analyze_transaction(session, wallet, sig)
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
            f"🔍 Whales: {len(WHALE_WALLETS)}\n"
            f"💰 Min Buy: ${MIN_WHALE_BUY_USD}\n"
            f"💧 Min Liquidity: ${MIN_LIQUIDITY_USD}\n"
            f"🛡️ Filters: Honeypot, Rug Pull, Scam\n"
            f"🧪 Mode: {'SIMULATION' if DRY_RUN else 'LIVE'}"
        )
        log(start_msg)
        await send_telegram(session, start_msg)
        tasks = [watch_whale(session, wallet) for wallet in WHALE_WALLETS]
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
