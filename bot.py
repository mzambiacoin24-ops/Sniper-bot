import asyncio
import aiohttp
import os
import base64
import struct
import time

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
HELIUS_RPC = os.getenv("HELIUS_RPC")

PUMPFUN_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

ACTIVE = False
CURRENT = None
USED = set()

ENTRY_PRICE = 0
PEAK = 0

TP = 1.5
SL = 0.35

async def send(session, msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    await session.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})

async def rpc(session, method, params):
    payload = {"jsonrpc":"2.0","id":1,"method":method,"params":params}
    async with session.post(HELIUS_RPC, json=payload) as r:
        return (await r.json()).get("result")

def extract(tx):
    try:
        instructions = tx["transaction"]["message"]["accountKeys"]
        balances = tx["meta"]["postTokenBalances"]

        mint = balances[0]["mint"]
        bonding = instructions[3]  # 👈 muhimu

        return mint, bonding
    except:
        return None, None

def price(data):
    try:
        sol = struct.unpack_from("<Q", data, 8)[0]
        token = struct.unpack_from("<Q", data, 16)[0]
        if token == 0:
            return 0
        return sol / token
    except:
        return 0

async def get_account(session, acc):
    res = await rpc(session, "getAccountInfo", [acc, {"encoding":"base64"}])
    if not res or not res.get("value"):
        return None
    return base64.b64decode(res["value"]["data"][0])

async def sniper():
    global ACTIVE, CURRENT, ENTRY_PRICE, PEAK

    async with aiohttp.ClientSession() as session:
        await send(session, "🔥 REAL SNIPER FIXED")

        while True:

            if ACTIVE:
                data = await get_account(session, CURRENT["bonding"])
                if data:
                    p = price(data)

                    if p > PEAK:
                        PEAK = p

                    profit = (p - ENTRY_PRICE) / ENTRY_PRICE

                    if PEAK >= ENTRY_PRICE * (1 + TP):
                        drop = (PEAK - p) / PEAK
                        if drop > 0.25:
                            await send(session, f"💰 SELL {CURRENT['mint']} {profit*100:.1f}%")
                            USED.add(CURRENT["mint"])
                            ACTIVE = False

                    elif p <= ENTRY_PRICE * (1 - SL):
                        await send(session, f"🛑 SELL {CURRENT['mint']} {profit*100:.1f}%")
                        USED.add(CURRENT["mint"])
                        ACTIVE = False

                await asyncio.sleep(3)
                continue

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

                CURRENT = {"mint": mint, "bonding": bonding}
                ENTRY_PRICE = p
                PEAK = p
                ACTIVE = True

                await send(session,
                    f"🚀 BUY\n{mint}\nPrice: {p:.8f}\nhttps://pump.fun/{mint}"
                )

                break

            await asyncio.sleep(2)

if __name__ == "__main__":
    asyncio.run(sniper())
