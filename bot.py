import asyncio
import aiohttp
import base64
import base58
import os
from solana.rpc.async_api import AsyncClient
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction

# ENV
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
HELIUS_RPC = os.getenv("HELIUS_RPC")

# WALLET
def load_wallet():
    return Keypair.from_bytes(base58.b58decode(PRIVATE_KEY))

# REAL BUY FUNCTION
async def real_buy(mint):
    try:
        wallet = load_wallet()
        client = AsyncClient(HELIUS_RPC)
        owner = wallet.pubkey()

        # 💰 balance
        balance = await client.get_balance(owner)
        amount = int(balance.value * 0.5)

        if amount < 10000:
            print("Balance ndogo sana")
            return False

        async with aiohttp.ClientSession() as session:

            # 🔁 STEP 1: GET QUOTE
            quote_url = f"https://quote-api.jup.ag/v6/quote?inputMint=So11111111111111111111111111111111111111112&outputMint={mint}&amount={amount}&slippageBps=1500"

            async with session.get(quote_url) as r:
                quote = await r.json()

            if "data" not in quote or not quote["data"]:
                print("No route")
                return False

            route = quote["data"][0]

            # 🔁 STEP 2: GET SWAP TX
            swap_url = "https://quote-api.jup.ag/v6/swap"
            payload = {
                "route": route,
                "userPublicKey": str(owner),
                "wrapUnwrapSOL": True
            }

            async with session.post(swap_url, json=payload) as r:
                swap_data = await r.json()

            tx_base64 = swap_data.get("swapTransaction")
            if not tx_base64:
                print("No tx")
                return False

            # 🔐 STEP 3: SIGN TX
            tx_bytes = base64.b64decode(tx_base64)
            tx = VersionedTransaction.from_bytes(tx_bytes)

            tx.sign([wallet])

            # 🚀 STEP 4: SEND TX
            result = await client.send_raw_transaction(tx.serialize())

            print("TX SENT:", result)

        await client.close()
        return True

    except Exception as e:
        print("ERROR:", e)
        return False

# TEST RUN
async def main():
    # mfano token (utabadilisha na pumpfun detection)
    mint = "EPjFWdd5AufqSSqeM2q4G9o2wJxzyy7f3Xv7h8aX7Zr"  # USDC

    success = await real_buy(mint)

    if success:
        print("BUY SUCCESS")
    else:
        print("BUY FAILED")

if __name__ == "__main__":
    asyncio.run(main())
