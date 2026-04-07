import asyncio
import aiohttp
import time
import os

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

ACTIVE_TRADE = False
seen_tokens = set()
positions = {}

# SETTINGS
MIN_BUYERS = 50
MIN_VOLUME = 2
MIN_MC = 3000
MAX_MC = 60000

STOP_LOSS = 0.30

async def send(session, msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    await session.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})

async def fetch_tokens(session):
    try:
        url = "https://pump.fun/api/recent"
        async with session.get(url) as r:
            data = await r.json()
            return data[:10]
    except:
        return []

def pass_filters(t):
    return (
        t.get("num_buyers", 0) >= MIN_BUYERS and
        t.get("volume", 0) >= MIN_VOLUME and
        MIN_MC <= t.get("market_cap", 0) <= MAX_MC
    )

async def snipe(session, t):
    global ACTIVE_TRADE

    mint = t.get("mint")
    mc = t.get("market_cap", 0)

    if not mint or mint in seen_tokens:
        return

    seen_tokens.add(mint)

    if ACTIVE_TRADE:
        return

    if not pass_filters(t):
        return

    ACTIVE_TRADE = True

    positions[mint] = {
        "entry_mc": mc,
        "highest_mc": mc,
        "sold": False
    }

    await send(session,
        f"🚀 BUY\n"
        f"🪙 {mint}\n"
        f"🔗 https://pump.fun/{mint}\n"
        f"📊 Entry MC: ${mc}"
    )

    asyncio.create_task(monitor(session, mint))

async def monitor(session, mint):
    global ACTIVE_TRADE

    while not positions[mint]["sold"]:
        try:
            async with aiohttp.ClientSession() as s:
                data = await fetch_tokens(s)

            token = next((x for x in data if x.get("mint") == mint), None)

            if not token:
                await asyncio.sleep(5)
                continue

            current_mc = token.get("market_cap", 0)
            entry_mc = positions[mint]["entry_mc"]

            # update peak
            if current_mc > positions[mint]["highest_mc"]:
                positions[mint]["highest_mc"] = current_mc

            highest = positions[mint]["highest_mc"]

            # 🔥 DYNAMIC TP (TRAILING)
            drop_from_peak = (highest - current_mc) / highest if highest > 0 else 0

            # 💰 TAKE PROFIT (trailing)
            if highest >= entry_mc * 2 and drop_from_peak >= 0.25:
                positions[mint]["sold"] = True
                ACTIVE_TRADE = False

                await send(session,
                    f"💰 SELL (TRAILING TP)\n"
                    f"🪙 {mint}\n"
                    f"📊 Peak MC: ${highest}\n"
                    f"📊 Exit MC: ${current_mc}\n"
                    f"🔗 https://pump.fun/{mint}"
                )
                break

            # 🛑 STOP LOSS
            if current_mc <= entry_mc * (1 - STOP_LOSS):
                positions[mint]["sold"] = True
                ACTIVE_TRADE = False

                await send(session,
                    f"🛑 SELL (SL)\n"
                    f"🪙 {mint}\n"
                    f"📉 MC: ${current_mc}\n"
                    f"🔗 https://pump.fun/{mint}"
                )
                break

            await asyncio.sleep(5)

        except:
            await asyncio.sleep(5)

async def scanner(session):
    await send(session, "🚀 REAL BONDING SNIPER STARTED")

    while True:
        tokens = await fetch_tokens(session)

        for t in tokens:
            await snipe(session, t)

        await asyncio.sleep(3)

async def main():
    async with aiohttp.ClientSession() as session:
        await scanner(session)

if __name__ == "__main__":
    asyncio.run(main())
