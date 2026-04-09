import asyncio
import aiohttp
import os
import base64
import struct
import time
from datetime import datetime

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
HELIUS_RPC = os.getenv("HELIUS_RPC")

PUMPFUN_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

TP = 1.20
SL = 0.25
TRAILING_DROP = 0.15
MAX_HOLD = 300

ACTIVE = False
CURRENT = None
USED = set()
ENTRY_PRICE = 0
PEAK = 0
START_TIME = 0

total_trades = 0
wins = 0
losses = 0
total_pnl = 0.0

def log(msg):
    now = datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] {msg}")

async def send(session, msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log(f"[NO TELEGRAM] {msg}")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        await session.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg,
            "disable_web_page_preview": True
        })
    except Exception as e:
        log(f"Telegram error: {e}")

async def rpc(session, method, params):
    try:
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        async with session.post(HELIUS_RPC, json=payload) as r:
            return (await r.json()).get("result")
    except:
        return None

def extract(tx):
    try:
        keys = tx["transaction"]["message"]["accountKeys"]
        balances = tx["meta"]["postTokenBalances"]
        if not balances:
            return None, None
        mint = balances[0]["mint"]
        bonding = keys[3] if isinstance(keys[3], str) else keys[3].get("pubkey", "")
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
    try:
        res = await rpc(session, "getAccountInfo", [acc, {"encoding": "base64"}])
        if not res or not res.get("value"):
            return None
        return base64.b64decode(res["value"]["data"][0])
    except:
        return None

async def sniper():
    global ACTIVE, CURRENT, ENTRY_PRICE, PEAK, START_TIME
    global total_trades, wins, losses, total_pnl

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID or not HELIUS_RPC:
        log("ERROR: Variables hazipo kwenye Railway!")
        log("Weka: TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, HELIUS_RPC")
        return

    async with aiohttp.ClientSession() as session:
        await send(session,
            f"🔥 PUMP.FUN SNIPER IMEANZA!\n"
            f"🎯 TP: +{(TP-1)*100:.0f}% | SL: -{SL*100:.0f}%\n"
            f"📉 Trailing Drop: -{TRAILING_DROP*100:.0f}%\n"
            f"⏱️ Max Hold: {MAX_HOLD//60} dakika\n"
            f"🧪 SIMULATION"
        )

        last_sig = None

        while True:
            try:
                if ACTIVE:
                    data = await get_account(session, CURRENT["bonding"])

                    if data:
                        p = price(data)

                        if p > PEAK:
                            PEAK = p

                        if p > 0 and ENTRY_PRICE > 0:
                            profit = (p - ENTRY_PRICE) / ENTRY_PRICE
                        else:
                            profit = 0

                        elapsed = time.time() - START_TIME
                        win_rate = (wins / max(total_trades, 1)) * 100

                        if elapsed > MAX_HOLD:
                            total_trades += 1
                            if profit > 0:
                                wins += 1
                            else:
                                losses += 1
                            total_pnl += profit
                            emoji = "💰" if profit > 0 else "📊"
                            await send(session,
                                f"⏱️ SELL (TIME)\n"
                                f"🪙 {CURRENT['mint'][:12]}...\n"
                                f"📈 PnL: {profit*100:+.1f}%\n"
                                f"📊 Jumla PnL: {total_pnl*100:+.1f}%\n"
                                f"🏆 Win Rate: {win_rate:.0f}% "
                                f"✅{wins} ❌{losses}"
                            )
                            USED.add(CURRENT["mint"])
                            ACTIVE = False
                            await asyncio.sleep(2)
                            continue

                        if PEAK >= ENTRY_PRICE * TP:
                            drop = (PEAK - p) / PEAK if PEAK > 0 else 0
                            if drop >= TRAILING_DROP:
                                total_trades += 1
                                wins += 1
                                total_pnl += profit
                                win_rate = (wins / max(total_trades, 1)) * 100
                                await send(session,
                                    f"💰 SELL (TP)\n"
                                    f"🪙 {CURRENT['mint'][:12]}...\n"
                                    f"📈 PnL: {profit*100:+.1f}%\n"
                                    f"📊 Jumla PnL: {total_pnl*100:+.1f}%\n"
                                    f"🏆 Win Rate: {win_rate:.0f}% "
                                    f"✅{wins} ❌{losses}"
                                )
                                USED.add(CURRENT["mint"])
                                ACTIVE = False
                                await asyncio.sleep(2)
                                continue

                        if p <= ENTRY_PRICE * (1 - SL):
                            total_trades += 1
                            losses += 1
                            total_pnl += profit
                            win_rate = (wins / max(total_trades, 1)) * 100
                            await send(session,
                                f"🛑 SELL (SL)\n"
                                f"🪙 {CURRENT['mint'][:12]}...\n"
                                f"📉 PnL: {profit*100:+.1f}%\n"
                                f"📊 Jumla PnL: {total_pnl*100:+.1f}%\n"
                                f"🏆 Win Rate: {win_rate:.0f}% "
                                f"✅{wins} ❌{losses}"
                            )
                            USED.add(CURRENT["mint"])
                            ACTIVE = False
                            await asyncio.sleep(2)
                            continue

                    await asyncio.sleep(3)
                    continue

                sigs = await rpc(session, "getSignaturesForAddress", [
                    PUMPFUN_PROGRAM, {"limit": 15}
                ])

                if not sigs:
                    await asyncio.sleep(2)
                    continue

                if last_sig is None:
                    last_sig = sigs[0]["signature"]
                    await asyncio.sleep(2)
                    continue

                new_sigs = []
                for s in sigs:
                    if s["signature"] == last_sig:
                        break
                    if not s.get("err"):
                        new_sigs.append(s["signature"])

                if new_sigs:
                    last_sig = sigs[0]["signature"]

                for s in new_sigs[:5]:
                    sig = s if isinstance(s, str) else s
                    tx = await rpc(session, "getTransaction", [
                        sig, {"encoding": "json", "maxSupportedTransactionVersion": 0}
                    ])
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
                    START_TIME = time.time()
                    ACTIVE = True

                    await send(session,
                        f"🚀 BUY\n"
                        f"🪙 {mint[:12]}...\n"
                        f"💲 Price: {p:.8f}\n"
                        f"🔗 https://pump.fun/{mint}\n"
                        f"🧪 SIMULATION"
                    )

                    log(f"BUY: {mint[:8]}... @ {p:.8f}")
                    break

                await asyncio.sleep(2)

            except Exception as e:
                log(f"Error: {e}")
                await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(sniper())
