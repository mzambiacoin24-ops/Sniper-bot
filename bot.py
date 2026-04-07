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

BUY_DELAY = 12   # ⏱️ subiri kabla ya kuingia
TP_TIME = 120    # 💰 strong coin
SL_TIME = 40     # 🛑 weak coin

async def send(session, msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    await session.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})

async def rpc(session, method, params):
    payload = {"jsonrpc":"2.0","id":1,"method":method,"params":params}
    async with session.post(HELIUS_RPC, json=payload) as r:
        return (await r.json()).get("result")

async def extract_mints(tx):
    try:
        return [t["mint"] for t in tx["meta"]["postTokenBalances"]]
    except:
        return []

# 🚀 SMART BUY (DELAY + CONFIRM)
async def smart_buy(session, mint):
    global ACTIVE_TRADE, CURRENT_TOKEN, ENTRY_TIME

    if ACTIVE_TRADE:
        return

    await send(session, f"⏳ WAITING CONFIRM\n{mint}")

    await asyncio.sleep(BUY_DELAY)

    # 🔍 confirm bado kuna activity
    sigs = await rpc(session, "getSignaturesForAddress", [PUMPFUN_PROGRAM, {"limit":10}])

    still_active = False

    for s in sigs:
        tx = await rpc(session, "getTransaction", [s["signature"], {"encoding":"json"}])
        if not tx:
            continue

        mints = await extract_mints(tx)
        if mint in mints:
            still_active = True
            break

    if not still_active:
        await send(session, f"❌ SKIPPED (DEAD TOKEN)\n{mint}")
        return

    # 🚀 BUY CONFIRMED
    ACTIVE_TRADE = True
    CURRENT_TOKEN = mint
    ENTRY_TIME = time.time()

    await send(session,
        f"🚀 BUY CONFIRMED\n{mint}\nhttps://pump.fun/{mint}"
    )

    asyncio.create_task(monitor_trade(session))

# 🔄 MONITOR
async def monitor_trade(session):
    global ACTIVE_TRADE, CURRENT_TOKEN

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

# 🔎 SCANNER
async def scan():
    async with aiohttp.ClientSession() as session:
        await send(session, "🔥 SMART SNIPER READY")

        last = None

        while True:
            sigs = await rpc(session, "getSignaturesForAddress", [PUMPFUN_PROGRAM, {"limit":20}])

            if not sigs:
                await asyncio.sleep(2)
                continue

            if not last:
                last = sigs[0]["signature"]
                await asyncio.sleep(2)
                continue

            new = []
            for s in sigs:
                if s["signature"] == last:
                    break
                new.append(s["signature"])

            if new:
                last = sigs[0]["signature"]

                for sig in new[:3]:
                    tx = await rpc(session, "getTransaction", [sig, {"encoding":"json"}])
                    if not tx:
                        continue

                    mints = await extract_mints(tx)

                    for mint in mints:
                        if not ACTIVE_TRADE:
                            asyncio.create_task(smart_buy(session, mint))

            await asyncio.sleep(2)

if __name__ == "__main__":
    asyncio.run(scan())
