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

TP_TIME = 120
SL_TIME = 60

seen_counts = {}

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

# 🔥 STRONG TOKEN (WITH MOMENTUM CHECK)
async def find_strong_token(session):
    global seen_counts

    sigs = await rpc(session, "getSignaturesForAddress", [PUMPFUN_PROGRAM, {"limit":20}])

    for s in sigs:
        tx = await rpc(session, "getTransaction", [s["signature"], {"encoding":"json"}])
        if not tx:
            continue

        mints = extract_mints(tx)

        for mint in mints:
            seen_counts[mint] = seen_counts.get(mint, 0) + 1

            # lazima ionekane mara 3
            if seen_counts[mint] >= 3:

                # ⏳ SUBIRI kidogo (momentum test)
                await asyncio.sleep(6)

                sigs2 = await rpc(session, "getSignaturesForAddress", [PUMPFUN_PROGRAM, {"limit":10}])

                still_alive = False

                for s2 in sigs2:
                    tx2 = await rpc(session, "getTransaction", [s2["signature"], {"encoding":"json"}])
                    if not tx2:
                        continue

                    mints2 = extract_mints(tx2)

                    if mint in mints2:
                        still_alive = True
                        break

                if still_alive:
                    return mint

    return None

# 🚀 MAIN
async def sniper():
    global ACTIVE_TRADE, CURRENT_TOKEN, ENTRY_TIME

    async with aiohttp.ClientSession() as session:
        await send(session, "🤖 ULTRA SNIPER (ANTI-SL)")

        while True:

            if ACTIVE_TRADE:
                await asyncio.sleep(2)
                continue

            mint = await find_strong_token(session)

            if not mint:
                await asyncio.sleep(2)
                continue

            ACTIVE_TRADE = True
            CURRENT_TOKEN = mint
            ENTRY_TIME = time.time()

            await send(session,
                f"🚀 BUY\n{mint}\nhttps://pump.fun/{mint}"
            )

            # 🔄 MONITOR
            while ACTIVE_TRADE:
                elapsed = time.time() - ENTRY_TIME

                if elapsed >= TP_TIME:
                    await send(session, f"💰 SELL (TP)\n{CURRENT_TOKEN}")
                    ACTIVE_TRADE = False
                    CURRENT_TOKEN = None
                    break

                if elapsed >= SL_TIME:
                    await send(session, f"🛑 SELL (SL)\n{CURRENT_TOKEN}")
                    ACTIVE_TRADE = False
                    CURRENT_TOKEN = None
                    break

                await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(sniper())
