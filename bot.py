import asyncio
import aiohttp
import os
import time

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
HELIUS_RPC = os.getenv("HELIUS_RPC")

PUMPFUN_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

ACTIVE_TRADE = False
CURRENT_TOKEN = None
ENTRY_TIME = 0

BUY_DELAY = 12
TP_TIME = 120
SL_TIME = 45

seen_mints = set()

async def send(session, msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    await session.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})

async def rpc(session, method, params):
    payload = {"jsonrpc":"2.0","id":1,"method":method,"params":params}
    async with session.post(HELIUS_RPC, json=payload) as r:
        return (await r.json()).get("result")

def extract_mints(tx):
    try:
        return [t["mint"] for t in tx["meta"]["postTokenBalances"]]
    except:
        return []

# 🚀 SMART PICK (NO SPAM)
async def find_token(session):
    sigs = await rpc(session, "getSignaturesForAddress", [PUMPFUN_PROGRAM, {"limit":15}])

    for s in sigs:
        tx = await rpc(session, "getTransaction", [s["signature"], {"encoding":"json"}])
        if not tx:
            continue

        mints = extract_mints(tx)

        for mint in mints:
            if mint not in seen_mints:
                seen_mints.add(mint)
                return mint

    return None

# 🚀 MAIN LOGIC
async def sniper():
    global ACTIVE_TRADE, CURRENT_TOKEN, ENTRY_TIME

    async with aiohttp.ClientSession() as session:
        await send(session, "🤖 SMART SNIPER READY")

        while True:

            # 🔒 kama kuna trade inaendelea → subiri
            if ACTIVE_TRADE:
                await asyncio.sleep(2)
                continue

            mint = await find_token(session)

            if not mint:
                await asyncio.sleep(2)
                continue

            # ⏳ delay (avoid fake pumps)
            await asyncio.sleep(BUY_DELAY)

            # 🚀 BUY ONE TOKEN ONLY
            ACTIVE_TRADE = True
            CURRENT_TOKEN = mint
            ENTRY_TIME = time.time()

            await send(session,
                f"🚀 BUY\n{mint}\nhttps://pump.fun/{mint}"
            )

            # 🔄 MONITOR HII TU
            while ACTIVE_TRADE:
                elapsed = time.time() - ENTRY_TIME

                if elapsed >= TP_TIME:
                    await send(session, f"💰 SELL (TP)\n{CURRENT_TOKEN}")
                    ACTIVE_TRADE = False
                    CURRENT_TOKEN = None
                    break

                if elapsed >= SL_TIME and elapsed < TP_TIME:
                    await send(session, f"🛑 SELL (SL)\n{CURRENT_TOKEN}")
                    ACTIVE_TRADE = False
                    CURRENT_TOKEN = None
                    break

                await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(sniper())
