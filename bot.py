import asyncio
import aiohttp
import os

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
HELIUS_RPC = os.getenv("HELIUS_RPC")

PUMPFUN_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

seen = set()

async def send(session, msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    await session.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})

async def rpc(session, method, params):
    payload = {"jsonrpc":"2.0","id":1,"method":method,"params":params}
    async with session.post(HELIUS_RPC, json=payload) as r:
        return (await r.json()).get("result")

# 🔥 REAL TOKEN DETECTION
async def extract_mints(tx):
    mints = []

    try:
        post = tx["meta"]["postTokenBalances"]

        for t in post:
            mint = t.get("mint")
            if mint and mint not in seen:
                seen.add(mint)
                mints.append(mint)

    except:
        pass

    return mints

async def scan():
    async with aiohttp.ClientSession() as session:
        await send(session, "🔥 REAL DETECTOR STARTED")

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

                for sig in new[:5]:
                    tx = await rpc(session, "getTransaction", [sig, {"encoding":"json"}])
                    if not tx:
                        continue

                    mints = await extract_mints(tx)

                    for mint in mints:
                        await send(session,
                            f"🆕 TOKEN DETECTED\n{mint}\nhttps://pump.fun/{mint}"
                        )

            await asyncio.sleep(2)

if __name__ == "__main__":
    asyncio.run(scan())
