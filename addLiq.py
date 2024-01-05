import time
import os
from algosdk.v2client import algod
from tinyman.assets import AssetAmount
from tinyman.v2.client import TinymanV2MainnetClient
from dotenv import load_dotenv

load_dotenv()

def get_algod():
    algod_server = os.getenv("ALGOD_MAINNET_SERVER")
    algod_token = os.getenv("ALGOD_MAINNET_TOKEN")
    algod_port = os.getenv("ALGOD_MAINNET_PORT")

    algod_address = f"{algod_server}:{algod_port}"
    return algod.AlgodClient(algod_token, algod_address)


def get_account_balance(algod_client, address, asset_id):
    account_info = algod_client.account_info(address)
    for asset in account_info['assets']:
        if asset['asset-id'] == asset_id:
            return asset['amount']
    return 0

while True:
    MINER_ADDRESS = os.getenv("MINER_ADDRESS")
    algod_client = get_algod()
    client = TinymanV2MainnetClient(algod_client=algod_client, user_address=MINER_ADDRESS)

    ASSET_ID = int(os.getenv("ASSET_ID"))  # Convert ASSET_ID to integer
    ASSET_A = client.fetch_asset(ASSET_ID)
    ASSET_B = client.fetch_asset(0)

    # Fetch the balance of ASSET_A for your account
    asset_a_balance = get_account_balance(algod_client, MINER_ADDRESS, ASSET_A.id)

    # Debug: Print the asset balance
    print(f"Asset Balance: {asset_a_balance}")

    # Handle case where asset balance is zero
    if asset_a_balance == 0:
        print("No asset balance available for liquidity. Skipping transaction.")
        time.sleep(15)  # Sleep and continue the loop
        continue

    pool = client.fetch_pool(ASSET_A.id, ASSET_B.id)

    quote = pool.fetch_single_asset_add_liquidity_quote(
        amount_a=AssetAmount(pool.asset_1, asset_a_balance),
    )

    txn_group = pool.prepare_add_liquidity_transactions_from_quote(quote=quote)

    if not client.asset_is_opted_in(asset_id=pool.pool_token_asset.id):
        # Opt-in to the pool token
        opt_in_txn_group = pool.prepare_pool_token_asset_optin_transactions()
        # Merge the transaction groups
        txn_group = txn_group + opt_in_txn_group

    # Sign transactions
    MINER_ADDRESS = os.getenv("MINER_ADDRESS")
    MINER_KEY = os.getenv("MINER_KEY")
    txn_group.sign_with_private_key(MINER_ADDRESS, MINER_KEY)

    # Submit transactions to the network and wait for confirmation
    try:
        txn_info = client.submit(txn_group, wait=True)
        pool.refresh()
        pool_position = pool.fetch_pool_position()
        share = pool_position["share"] * 100
        print(f"Success! Added {asset_a_balance} units of Asset {ASSET_A.id} to the pool.")
    except Exception as e:
        print(f"Not enough funds. Will try again in 15 seconds. Error: {str(e)}")
    
    # Sleep for 180 seconds before running again
    time.sleep(180)
