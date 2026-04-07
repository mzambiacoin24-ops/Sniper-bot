import asyncio
import aiohttp
import base64
import base58
import os
from solana.rpc.async_api import AsyncClient
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction

PRIVATE_KEY = os.getenv("PRIVATE_KEY")
HELIUS_RPC = os.getenv("HELIUS_RPC")

def load_wallet():
    return Keypair.from_bytes(base58.b58decode(PRIVATE_KEY))

async def real_buy(mint):
    try:
        print("START BUY...")

        wallet = load_wallet()
        client = AsyncClient(HELIUS_RPC)
        owner = wallet.pubkey()

        balance = await client.get_balance(owner)
        amount = int(balance.value * 0.5)

        print("BALANCE:", balance.value)

        if amount < 10000:
            print("Balance ndogo sana")
            return False

        async with aiohttp.ClientSession() as session:

            print("GET QUOTE...")

            quote_url = f"https://quote-api.jup.ag/v6/quote?inputMint=So11111111111111111111111111111111111111112&outputMint={mint}&amount={amount}&slippageBps=1500"

            async with session.get(quote_url) as r:
                quote = await r.json()

            if "data" not in quote or not quote["data"]:
                print("No route")
                return False

            route = quote["data"][0]

            print("GET SWAP TX...")

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

            print("SIGNING TX...")

            tx_bytes = base64.b64decode(tx_base64)
            tx = VersionedTransaction.from_bytes(tx_bytes)

            # 🔥 SIGN FIX
            tx = VersionedTransaction(tx.message, [wallet])

            print("SENDING TX...")

            result = await client.send_raw_transaction(bytes(tx))

            print("TX SENT:", result)

        await client.close()
        return True

    except Exception as e:
        print("ERROR:", e)
        return False


async def main():
    print("BOT STARTED...")

    mint = "EPjFWdd5AufqSSqeM2q4G9o2wJxzyy7f3Xv7h8aX7Zr"

    success = await real_buy(mint)

    if success:
        print("BUY SUCCESS")
    else:
        print("BUY FAILED")


if __name__ == "__main__":
    asyncio.run(main())
