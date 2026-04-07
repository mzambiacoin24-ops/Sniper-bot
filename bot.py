import asyncio
import aiohttp
import time
import random
from datetime import datetime

TELEGRAM_TOKEN = "8778061073:AAFvbdcKusf3P74VLTzdcYa7obV2LrgDXyE"
TELEGRAM_CHAT_ID = "7010983039"
HELIUS_RPC = "https://mainnet.helius-rpc.com/?api-key=04e4a6db-29bd-4b08-99d9-46ad23e9feb1"
JUPITER_API = "https://quote-api.jup.ag/v6"

PUMPFUN_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
SOL_MINT = "So11111111111111111111111111111111111111112"

DRY_RUN = True

BUY_AMOUNT_SOL = 0.05
TAKE_PROFIT_X = 3.0
STOP_LOSS_PCT = 0.30
MAX_HOLD_MINUTES = 20

TOTAL_SUPPLY = 1_000_000_000
GRADUATION_MCAP = 69_000
INITIAL_PRICE = 0.000001

sniped_tokens = {}
processed_sigs = set()
seen_mints = set()

stats = {
    "total_launches": 0,
    "sniped": 0,
    "wins": 0,
    "losses": 0,
    "total_pnl_sol": 0.0,
    "graduated": 0
}

def log(msg):
    now = datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] {msg}")

async def send_telegram(session, msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        await session.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})
    except Exception as e:
        log(f"Telegram error: {e}")

async def helius_rpc(session, method, params):
    try:
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        async with session.post(HELIUS_RPC, json=payload) as r:
            data = await r.json()
            return data.get("result")
    except:
        return None

async def get_sol_price(session):
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd"
        async with session.get(url) as r:
            data = await r.json()
            return float(data["solana"]["usd"])
    except:
        return 85.0

class BondingCurve:
    def __init__(self, token_mint, sol_price):
        self.token_mint = token_mint
        self.sol_price = sol_price
        self.current_price_usd = INITIAL_PRICE
        self.market_cap_usd = INITIAL_PRICE * TOTAL_SUPPLY
        self.graduated = False
        self.buyers = 0
        self.last_update = time.time()

    def simulate_market_activity(self):
        elapsed = time.time() - self.last_update
        self.last_update = time.time()

        activity = random.random()

        if self.market_cap_usd < 1000:
            if activity < 0.7:
                change = random.uniform(0.02, 0.15)
                self.buyers += random.randint(1, 5)
            else:
                change = random.uniform(-0.05, -0.01)
        elif self.market_cap_usd < 10000:
            if activity < 0.6:
                change = random.uniform(0.01, 0.08)
                self.buyers += random.randint(1, 3)
            else:
                change = random.uniform(-0.08, -0.02)
        elif self.market_cap_usd < 40000:
            if activity < 0.5:
                change = random.uniform(0.005, 0.05)
            else:
                change = random.uniform(-0.10, -0.01)
        else:
            if activity < 0.45:
                change = random.uniform(0.003, 0.03)
            else:
                change = random.uniform(-0.15, -0.01)

        self.current_price_usd *= (1 + change)
        self.market_cap_usd = self.current_price_usd * TOTAL_SUPPLY

        if self.market_cap_usd >= GRADUATION_MCAP:
            self.graduated = True

        return self.current_price_usd

    def get_status(self):
        progress = min((self.market_cap_usd / GRADUATION_MCAP) * 100, 100)
        return {
            "price_usd": self.current_price_usd,
            "mcap_usd": self.market_cap_usd,
            "progress": progress,
            "buyers": self.buyers,
            "graduated": self.graduated
        }

async def simulate_bonding_curve_trade(session, token_mint, creator):
    if token_mint in sniped_tokens:
        return

    sol_price = await get_sol_price(session)
    curve = BondingCurve(token_mint, sol_price)

    curve.simulate_market_activity()
    curve.simulate_market_activity()
    curve.simulate_market_activity()

    entry_price_usd = curve.current_price_usd
    tokens_bought = (BUY_AMOUNT_SOL * sol_price) / entry_price_usd
    entry_mcap = curve.market_cap_usd

    stats["sniped"] += 1

    sniped_tokens[token_mint] = {
        "curve": curve,
        "entry_price_usd": entry_price_usd,
        "tokens_bought": tokens_bought,
        "entry_time": time.time(),
        "entry_mcap": entry_mcap,
        "creator": creator or "Unknown",
        "buy_sol": BUY_AMOUNT_SOL,
        "sold": False
    }

    msg = (
        f"🚀 BONDING CURVE SNIPE!\n"
        f"🪙 Token: {token_mint[:8]}...\n"
        f"👤 Creator: {(creator or 'Unknown')[:8]}...\n"
        f"💰 Kununua: {BUY_AMOUNT_SOL} SOL (${BUY_AMOUNT_SOL*sol_price:.2f})\n"
        f"💲 Bei entry: ${entry_price_usd:.8f}\n"
        f"🪙 Tokens: {tokens_bought:,.0f}\n"
        f"📊 Market Cap: ${entry_mcap:,.0f}\n"
        f"📈 Progress: {(entry_mcap/GRADUATION_MCAP)*100:.1f}% → $69k\n"
        f"🎯 TP: {TAKE_PROFIT_X}x | SL: -{STOP_LOSS_PCT*100:.0f}%\n"
        f"🧪 BONDING CURVE SIMULATION"
    )
    log(msg)
    await send_telegram(session, msg)

    asyncio.create_task(monitor_bonding_curve(session, token_mint))

async def monitor_bonding_curve(session, token_mint):
    await asyncio.sleep(5)

    if token_mint not in sniped_tokens:
        return

    position = sniped_tokens[token_mint]
    curve = position["curve"]
    entry_price = position["entry_price_usd"]
    tokens = position["tokens_bought"]
    sol_price = await get_sol_price(session)

    update_count = 0

    while not position["sold"]:
        try:
            current_price = curve.simulate_market_activity()
            status = curve.get_status()
            elapsed_min = (time.time() - position["entry_time"]) / 60
            multiplier = current_price / entry_price
            change_pct = (multiplier - 1) * 100
            current_value_usd = tokens * current_price
            entry_value_usd = tokens * entry_price
            pnl_usd = current_value_usd - entry_value_usd
            pnl_sol = pnl_usd / sol_price
            update_count += 1

            if update_count % 10 == 0:
                log(
                    f"📊 {token_mint[:8]}... | "
                    f"{multiplier:.2f}x | "
                    f"MCap: ${status['mcap_usd']:,.0f} | "
                    f"Progress: {status['progress']:.1f}%"
                )

            if status["graduated"]:
                final_pnl_sol = pnl_sol
                stats["wins"] += 1
                stats["total_pnl_sol"] += final_pnl_sol
                stats["graduated"] += 1
                position["sold"] = True
                msg = (
                    f"🎓 GRADUATED TO RAYDIUM!\n"
                    f"🪙 Token: {token_mint[:8]}...\n"
                    f"📈 Bei: {multiplier:.1f}x (+{change_pct:.0f}%)\n"
                    f"📊 Final MCap: ${status['mcap_usd']:,.0f}\n"
                    f"💰 PnL: +{final_pnl_sol:.4f} SOL (${final_pnl_sol*sol_price:.2f})\n"
                    f"📊 Total PnL: {stats['total_pnl_sol']:.4f} SOL\n"
                    f"🎉 Token imefanikiwa!\n"
                    f"🧪 SIMULATION"
                )
                await send_telegram(session, msg)
                break

            elif multiplier >= TAKE_PROFIT_X:
                stats["wins"] += 1
                stats["total_pnl_sol"] += pnl_sol
                position["sold"] = True
                msg = (
                    f"💰 TAKE PROFIT!\n"
                    f"🪙 Token: {token_mint[:8]}...\n"
                    f"📈 {multiplier:.1f}x (+{change_pct:.0f}%)\n"
                    f"📊 MCap: ${status['mcap_usd']:,.0f}\n"
                    f"💵 PnL: +{pnl_sol:.4f} SOL (${pnl_sol*sol_price:.2f})\n"
                    f"📊 Total PnL: {stats['total_pnl_sol']:.4f} SOL\n"
                    f"🧪 SIMULATION"
                )
                await send_telegram(session, msg)
                break

            elif (1 - multiplier) >= STOP_LOSS_PCT:
                loss_sol = position["buy_sol"] * STOP_LOSS_PCT
                stats["losses"] += 1
                stats["total_pnl_sol"] -= loss_sol
                position["sold"] = True
                msg = (
                    f"🛑 STOP LOSS!\n"
                    f"🪙 Token: {token_mint[:8]}...\n"
                    f"📉 {multiplier:.2f}x ({change_pct:.0f}%)\n"
                    f"📊 MCap: ${status['mcap_usd']:,.0f}\n"
                    f"💸 PnL: -{loss_sol:.4f} SOL\n"
                    f"📊 Total PnL: {stats['total_pnl_sol']:.4f} SOL\n"
                    f"🧪 SIMULATION"
                )
                await send_telegram(session, msg)
                break

            elif elapsed_min >= MAX_HOLD_MINUTES:
                if pnl_sol > 0:
                    stats["wins"] += 1
                else:
                    stats["losses"] += 1
                stats["total_pnl_sol"] += pnl_sol
                position["sold"] = True
                msg = (
                    f"⏱️ MUDA UMEISHA — INAOUZA!\n"
                    f"🪙 Token: {token_mint[:8]}...\n"
                    f"📊 {multiplier:.2f}x ({change_pct:+.1f}%)\n"
                    f"📊 MCap: ${status['mcap_usd']:,.0f}\n"
                    f"💵 PnL: {pnl_sol:+.4f} SOL (${pnl_sol*sol_price:.2f})\n"
                    f"📊 Total PnL: {stats['total_pnl_sol']:.4f} SOL\n"
                    f"🧪 SIMULATION"
                )
                await send_telegram(session, msg)
                break

            await asyncio.sleep(8)

        except Exception as e:
            log(f"Monitor error: {e}")
            await asyncio.sleep(10)

async def parse_new_tokens(session, signature):
    try:
        result = await helius_rpc(session, "getTransaction", [
            signature,
            {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}
        ])
        if not result:
            return []

        meta = result.get("meta", {})
        if meta.get("err"):
            return []

        pre_balances = meta.get("preTokenBalances", [])
        post_balances = meta.get("postTokenBalances", [])
        pre_mints = {b["mint"] for b in pre_balances}

        new_tokens = []
        for b in post_balances:
            mint = b.get("mint", "")
            if mint and mint not in pre_mints and mint != SOL_MINT and mint not in seen_mints:
                owner = b.get("owner", "")
                new_tokens.append({"mint": mint, "owner": owner})
                seen_mints.add(mint)

        return new_tokens

    except:
        return []

async def poll_pumpfun(session):
    log("Inaanza polling Pump.fun...")
    await send_telegram(session, "🎯 Pump.fun Bonding Curve Sniper inaanza...")

    last_sig = None

    while True:
        try:
            params = [PUMPFUN_PROGRAM, {"limit": 10, "commitment": "confirmed"}]
            if last_sig:
                params[1]["until"] = last_sig

            sigs = await helius_rpc(session, "getSignaturesForAddress", params)

            if not sigs:
                await asyncio.sleep(2)
                continue

            if last_sig is None:
                last_sig = sigs[0]["signature"]
                log("Imeanzishwa. Inasubiri tokens mpya...")
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

                for sig in new_sigs[:3]:
                    if sig in processed_sigs:
                        continue
                    processed_sigs.add(sig)

                    new_tokens = await parse_new_tokens(session, sig)

                    for token_info in new_tokens:
                        mint = token_info["mint"]
                        creator = token_info["owner"]
                        stats["total_launches"] += 1
                        log(f"🆕 Token mpya #{stats['total_launches']}: {mint[:8]}...")
                        await simulate_bonding_curve_trade(session, mint, creator)

            await asyncio.sleep(2)

        except Exception as e:
            log(f"Poll error: {e}")
            await asyncio.sleep(5)

async def print_stats(session):
    while True:
        await asyncio.sleep(300)
        sol_price = await get_sol_price(session)
        win_rate = (stats["wins"] / max(stats["sniped"], 1)) * 100
        msg = (
            f"📊 RIPOTI YA DAKIKA 5\n"
            f"🚀 Launches: {stats['total_launches']}\n"
            f"🎯 Sniped: {stats['sniped']}\n"
            f"✅ Wins: {stats['wins']} | ❌ Losses: {stats['losses']}\n"
            f"🎓 Graduated: {stats['graduated']}\n"
            f"📈 Win Rate: {win_rate:.1f}%\n"
            f"💰 Total PnL: {stats['total_pnl_sol']:.4f} SOL\n"
            f"💵 USD: ${stats['total_pnl_sol']*sol_price:.2f}\n"
            f"🧪 BONDING CURVE SIMULATION"
        )
        log(msg)
        await send_telegram(session, msg)

async def main():
    async with aiohttp.ClientSession() as session:
        sol_price = await get_sol_price(session)
        start_msg = (
            f"🎯 PUMP.FUN BONDING CURVE SNIPER!\n"
            f"📈 Bonding Curve Simulation: ACTIVE\n"
            f"💰 Buy: {BUY_AMOUNT_SOL} SOL (${BUY_AMOUNT_SOL*sol_price:.2f})\n"
            f"🎯 Take Profit: {TAKE_PROFIT_X}x\n"
            f"🛑 Stop Loss: -{STOP_LOSS_PCT*100:.0f}%\n"
            f"🎓 Graduation Target: ${GRADUATION_MCAP:,}\n"
            f"⏱️ Max Hold: {MAX_HOLD_MINUTES} dakika\n"
            f"🧪 Mode: BONDING CURVE SIMULATION"
        )
        log(start_msg)
        await send_telegram(session, start_msg)

        await asyncio.gather(
            poll_pumpfun(session),
            print_stats(session)
        )

if __name__ == "__main__":
    asyncio.run(main())
