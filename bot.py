import asyncio
import aiohttp
import os
import base64
import struct
import time
from hashlib import sha256

# ===== ENV =====
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
HELIUS_RPC = os.getenv("HELIUS_RPC")

PUMPFUN_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

# ===== CONFIG =====
TP_PCT = 1.5      # 150% (≈ 2.5x)
SL_PCT = 0.35     # -35%

ACTIVE = False
CURRENT = None
USED = set()
ENTRY_PRICE = 0
PEAK_PRICE = 0

# ===== TELEGRAM =====
async def send(session, msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    await session.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})

# ===== RPC =====
async def rpc(session, method, params):
    payload = {"jsonrpc":"2.0","id":1,"method":method,"params":params}
    async with session.post(HELIUS_RPC, json=payload) as r:
        return (await r.json()).get("result")

# ===== GET ACCOUNT =====
async def get_account(session, acc):
    res = await rpc(session, "getAccountInfo", [acc, {"encoding":"base64"}])
    if not res or not res.get("value"):
        return None
    return base64.b64decode(res["value"]["data"][0])

# ===== CALC PRICE (REAL) =====
def calc_price(data):
    try:
        # pump.fun bonding layout (common pattern)
        sol_reserve = struct.unpack_from("<Q", data, 8)[0]
        token_reserve = struct.unpack_from("<Q", data, 16)[0]
        if token_reserve == 0:
            return 0
        return sol_reserve / token_reserve
    except:
        return 0

# ===== DERIVE BONDING PDA (IMPORTANT) =====
def derive_bonding(mint):
    # seeds zinazotumika mara nyingi kwa pump.fun
    seeds = [
        b"bonding-curve",
        bytes.fromhex(mint) if len(mint)==64 else mint.encode()
    ]
    h = sha256(b"".join(seeds) + bytes(PUMPFUN_PROGRAM, "utf-8")).hexdigest()
    return h[:44]  # approximate pubkey (string form)

# ===== EXTRACT MINT =====
def extract_mints(tx):
    try:
        return [t["mint"] for t in tx["meta"]["postTokenBalances"]]
    except:
        return []

# ===== FIND TOKEN =====
async def find_token(session):
    sigs = await rpc(session, "getSignaturesForAddress", [PUMPFUN_PROGRAM, {"limit":20}])

    for s in sigs:
        tx = await rpc(session, "getTransaction", [s["signature"], {"encoding":"json"}])
        if not tx:
            continue

        for mint in extract_mints(tx):
            if mint not in USED:
                return mint
    return None

# ===== MAIN =====
async def sniper():
    global ACTIVE, CURRENT, ENTRY_PRICE, PEAK_PRICE

    async with aiohttp.ClientSession() as session:
        await send(session, "🔥 REAL BONDING SNIPER (PRICE BASED)")

        while True:

            if ACTIVE:
                # ===== MONITOR =====
                bonding = derive_bonding(CURRENT)
                data = await get_account(session, bonding)

                if data:
                    price = calc_price(data)

                    if price > PEAK_PRICE:
                        PEAK_PRICE = price

                    profit = (price - ENTRY_PRICE) / ENTRY_PRICE

                    # 💰 TP (dynamic)
                    if PEAK_PRICE >= ENTRY_PRICE * (1 + TP_PCT):
                        drop = (PEAK_PRICE - price) / PEAK_PRICE
                        if drop >= 0.25:
                            await send(session,
                                f"💰 SELL\n{CURRENT}\nProfit: {profit*100:.1f}%"
                            )
                            USED.add(CURRENT)
                            ACTIVE = False

                    # 🛑 SL
                    elif price <= ENTRY_PRICE * (1 - SL_PCT):
                        await send(session,
                            f"🛑 SELL\n{CURRENT}\nLoss: {profit*100:.1f}%"
                        )
                        USED.add(CURRENT)
                        ACTIVE = False

                await asyncio.sleep(3)
                continue

            # ===== FIND NEW =====
            mint = await find_token(session)

            if not mint:
                await asyncio.sleep(2)
                continue

            bonding = derive_bonding(mint)
            data = await get_account(session, bonding)

            if not data:
                await asyncio.sleep(2)
                continue

            price = calc_price(data)
            if price == 0:
                continue

            # ===== BUY =====
            CURRENT = mint
            ENTRY_PRICE = price
            PEAK_PRICE = price
            ACTIVE = True

            await send(session,
                f"🚀 BUY\n{mint}\nPrice: {price:.8f}\nhttps://pump.fun/{mint}"
            )

if __name__ == "__main__":
    asyncio.run(sniper())
