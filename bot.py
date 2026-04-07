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

ACTIVE_TRADE = False
seen = set()
positions = {}

STOP_LOSS = 0.30

# 📩 TELEGRAM
async def send(session, msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    await session.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})

# 🔗 RPC
async def rpc(session, method, params):
    payload = {"jsonrpc":"2.0","id":1,"method":method,"params":params}
    async with session.post(HELIUS_RPC, json=payload) as r:
        return (await r.json()).get("result")

# 🔍 GET TX
async def get_tx(session, sig):
    return await rpc(session, "getTransaction", [sig, {"encoding":"json"}])

# 🔍 GET ACCOUNT DATA
async def get_account(session, acc):
    res = await rpc(session, "getAccountInfo", [acc, {"encoding":"base64"}])
    if not res or not res.get("value"):
        return None
    return base64.b64decode(res["value"]["data"][0])

# 💣 PRICE (REAL)
def calc_price(data):
    try:
        sol = struct.unpack_from("<Q", data, 8)[0]
        tok = struct.unpack_from("<Q", data, 16)[0]
        if tok == 0:
            return 0
        return sol / tok
    except:
        return 0

# 🔥 FIND BONDING ACCOUNT
def find_bonding_account(tx):
    try:
        accounts = tx["transaction"]["message"]["accountKeys"]

        # heuristic: account yenye data kubwa (later tunathibitisha)
        return accounts[-1]
    except:
        return None

# 🚀 SNIPE
async def snipe(session, mint, bonding):
    global ACTIVE_TRADE

    if ACTIVE_TRADE:
        return

    data = await get_account(session, bonding)
    if not data:
        return

    price = calc_price(data)
    if price == 0:
        return

    ACTIVE_TRADE = True

    positions[mint] = {
        "entry": price,
        "peak": price,
        "bonding": bonding
    }

    await send(session,
        f"🚀 BUY\n{mint}\n🔗 https://pump.fun/{mint}\n💰 Price: {price:.8f}"
    )

    asyncio.create_task(monitor(session, mint))

# 🔄 MONITOR
async def monitor(session, mint):
    global ACTIVE_TRADE

    pos = positions[mint]

    while True:
        data = await get_account(session, pos["bonding"])
        if not data:
            await asyncio.sleep(2)
            continue

        price = calc_price(data)

        if price > pos["peak"]:
            pos["peak"] = price

        drop = (pos["peak"] - price) / pos["peak"]

        # 💰 TP
        if pos["peak"] >= pos["entry"] * 2 and drop >= 0.25:
            ACTIVE_TRADE = False
            await send(session,
                f"💰 SELL\n{mint}\n📈 Peak: {pos['peak']:.8f}\n📉 Exit: {price:.8f}"
            )
            break

        # 🛑 SL
        if price <= pos["entry"] * (1 - STOP_LOSS):
            ACTIVE_TRADE = False
            await send(session,
                f"🛑 SELL\n{mint}\nPrice: {price:.8f}"
            )
            break

        await asyncio.sleep(3)

# 🔎 SCAN
async def scan(session):
    await send(session, "🔥 REAL SNIPER LIVE")

    last = None

    while True:
        try:
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

                for sig in new[:5]:
                    tx = await get_tx(session, sig)
                    if not tx:
                        continue

                    mint = None
                    try:
                        for ins in tx["transaction"]["message"]["instructions"]:
                            mint = ins.get("parsed", {}).get("info", {}).get("mint")
                            if mint:
                                break
                    except:
                        continue

                    if not mint or mint in seen:
                        continue

                    seen.add(mint)

                    bonding = find_bonding_account(tx)
                    if not bonding:
                        continue

                    await snipe(session, mint, bonding)

            await asyncio.sleep(2)

        except:
            await asyncio.sleep(3)

async def main():
    async with aiohttp.ClientSession() as session:
        await scan(session)

if __name__ == "__main__":
    asyncio.run(main())
