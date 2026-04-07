import asyncio
import aiohttp
import time
from datetime import datetime
import os
import base58

from solana.rpc.async_api import AsyncClient
from solders.keypair import Keypair
from solders.system_program import transfer, TransferParams

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
HELIUS_RPC = os.getenv("HELIUS_RPC")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")

PUMPFUN_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
SOL_MINT = "So11111111111111111111111111111111111111112"

ACTIVE_TRADE = False

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

async def send(session, msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    await session.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})

async def helius(session, method, params):
    payload = {"jsonrpc":"2.0","id":1,"method":method,"params":params}
    async with session.post(HELIUS_RPC, json=payload) as r:
        data = await r.json()
        return data.get("result")

def load_wallet():
    secret = base58.b58decode(PRIVATE_KEY)
    return Keypair.from_bytes(secret)

# 🔥 TEST TRANSACTION (REAL)
async def real_buy(session, mint):
    try:
        client = AsyncClient(HELIUS_RPC)
        wallet = load_wallet()

        lamports = 1000000  # 0.001 SOL

        tx = transfer(
            TransferParams(
                from_pubkey=wallet.pubkey(),
                to_pubkey=wallet.pubkey(),
                lamports=lamports
            )
        )

        result = await client.send_transaction(tx, wallet)

        log(f"TX SENT: {result}")

        await client.close()
        return True

    except Exception as e:
        log(f"ERROR: {e}")
        return False

async def get_tokens(session, sig):
    try:
        tx = await helius(session, "getTransaction", [sig, {"encoding":"jsonParsed"}])
        if not tx:
            return []

        instructions = tx["transaction"]["message"]["instructions"]
        tokens = []

        for i in instructions:
            info = i.get("parsed", {}).get("info", {})
            mint = info.get("mint")

            if mint and mint != SOL_MINT:
                tokens.append(mint)

        return tokens
    except:
        return []

def pass_filters(mint):
    return len(mint) > 30

# 🚀 SNIPE (FIXED — NO SPAM)
async def snipe(session, mint):
    global ACTIVE_TRADE

    if ACTIVE_TRADE:
        return

    if not pass_filters(mint):
        return

    ACTIVE_TRADE = True

    await send(session, f"🚀 BUYING {mint[:6]}...")

    success = await real_buy(session, mint)

    if success:
        await send(session, f"✅ TX SENT {mint[:6]}")
    else:
        await send(session, f"❌ FAILED {mint[:6]}")

    ACTIVE_TRADE = False

# 🔎 SCAN
async def scan(session):
    await send(session, "🚀 REAL SNIPER (TEST MODE)")

    last = None

    while True:
        try:
            sigs = await helius(session, "getSignaturesForAddress", [PUMPFUN_PROGRAM, {"limit":10}])

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

                for sig in new[:2]:
                    tokens = await get_tokens(session, sig)

                    for mint in tokens:
                        await snipe(session, mint)

            await asyncio.sleep(2)

        except Exception as e:
            log(e)
            await asyncio.sleep(5)

async def main():
    async with aiohttp.ClientSession() as session:
        await send(session, "🚀 BOT STARTED (REAL TEST MODE)")
        await scan(session)

if __name__ == "__main__":
    asyncio.run(main())
