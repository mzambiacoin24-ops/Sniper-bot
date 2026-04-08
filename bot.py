import asyncio
import aiohttp
import os
import base64
import struct
import time

# ===== ENV =====
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
HELIUS_RPC = os.getenv("HELIUS_RPC")

PUMPFUN_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

# ===== CONFIG =====
TP = 1.2        # 20% profit (mapema kidogo kupata TP)
SL = 0.25       # 25% loss
MAX_HOLD = 180  # sekunde 180 = dakika 3

# ===== STATE =====
ACTIVE = False
CURRENT = None
USED = set()

ENTRY_PRICE = 0
PEAK = 0
START_TIME = 0

# ===== TELEGRAM =====
async def send(session, msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    await session.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})

# ===== RPC =====
async def rpc(session, method, params):
    payload = {"jsonrpc":"2.0","id":1,"method":method,"params":params}
    async with session.post(HELIUS_RPC, json=payload) as r:
        return (await r.json()).get("result")

# ===== EXTRACT MINT + BONDING =====
def extract(tx):
    try:
        keys = tx["transaction"]["message"]["accountKeys"]
        balances = tx["meta"]["postTokenBalances"]

        mint = balances[0]["mint"]
        bonding = keys[3]   # pump.fun bonding account

        return mint, bonding
    except:
        return None, None

# ===== PRICE =====
def price(data):
    try:
        sol = struct.unpack_from("<Q", data, 8)[0]
        token = struct.unpack_from("<Q", data, 16)[0]
        if token == 0:
            return 0
        return sol / token
    except:
        return 0

# ===== GET ACCOUNT =====
async def get_account(session, acc):
    res = await rpc(session, "getAccountInfo", [acc, {"encoding":"base64"}])
    if not res or not res.get("value"):
        return None
    return base64.b64decode(res["value"]["data"][0])

# ===== MAIN =====
async def sniper():
    global ACTIVE, CURRENT, ENTRY_PRICE, PEAK, START_TIME

    async with aiohttp.ClientSession() as session:
        await send(session, "🔥 FINAL REAL SNIPER (STABLE)")

        while True:

            # ================= MONITOR =================
            if ACTIVE:
                data = await get_account(session, CURRENT["bonding"])

                if data:
                    p = price(data)

                    if p > PEAK:
                        PEAK = p

                    profit = (p - ENTRY_PRICE) / ENTRY_PRICE

                    # ⏱️ TIME EXIT
                    if time.time() - START_TIME > MAX_HOLD:
                        await send(session,
                            f"⏱️ SELL (TIME)\n{CURRENT['mint']}\nPnL: {profit*100:.1f}%"
                        )
                        USED.add(CURRENT["mint"])
                        ACTIVE = False
                        continue

                    # 💰 TP (peak drop logic)
                    if PEAK >= ENTRY_PRICE * (1 + TP):
                        drop = (PEAK - p) / PEAK
                        if drop >= 0.2:
                            await send(session,
                                f"💰 SELL (TP)\n{CURRENT['mint']}\nPnL: {profit*100:.1f}%"
                            )
                            USED.add(CURRENT["mint"])
                            ACTIVE = False
                            continue

                    # 🛑 SL
                    if p <= ENTRY_PRICE * (1 - SL):
                        await send(session,
                            f"🛑 SELL (SL)\n{CURRENT['mint']}\nPnL: {profit*100:.1f}%"
                        )
                        USED.add(CURRENT["mint"])
                        ACTIVE = False
                        continue

                await asyncio.sleep(3)
                continue

            # ================= FIND TOKEN =================
            sigs = await rpc(session, "getSignaturesForAddress", [PUMPFUN_PROGRAM, {"limit":15}])

            for s in sigs:
                tx = await rpc(session, "getTransaction", [s["signature"], {"encoding":"json"}])
                if not tx:
                    continue

                mint, bonding = extract(tx)

                if not mint or mint in USED:
                    continue

                data = await get_account(session, bonding)
                if not data:
                    continue

                p = price(data)
                if p == 0:
                    continue

                # 🚀 BUY
                CURRENT = {"mint": mint, "bonding": bonding}
                ENTRY_PRICE = p
                PEAK = p
                START_TIME = time.time()
                ACTIVE = True

                await send(session,
                    f"🚀 BUY\n{mint}\nPrice: {p:.8f}\nhttps://pump.fun/{mint}"
                )

                break

            await asyncio.sleep(2)

if __name__ == "__main__":
    asyncio.run(sniper())
