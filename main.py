import click
import algosdk
from dotenv import load_dotenv
import os
import math
import base64
import time
from algosdk.atomic_transaction_composer import (
    AtomicTransactionComposer,
    AccountTransactionSigner,
)
from threading import Thread, Lock
from datetime import datetime

load_dotenv()

miner_mnemonic = os.getenv("MINER_MNEMONIC")
try:
    miner_sk = algosdk.mnemonic.to_private_key(miner_mnemonic)
    miner_signer = AccountTransactionSigner(miner_sk)
    miner_address = algosdk.account.address_from_private_key(miner_sk)
except Exception:
    click.secho(f"Miner mnemonic is malformed.", fg="red")
    exit(1)

deposit_mnemonic = os.getenv("DEPOSIT_MNEMONIC")
try:
    deposit_pk = algosdk.mnemonic.to_private_key(deposit_mnemonic)
    deposit_address = algosdk.account.address_from_private_key(deposit_pk)
except Exception:
    deposit_pk = None
    deposit_address = os.getenv("DEPOSIT_ADDRESS")
if not algosdk.encoding.is_valid_address(deposit_address):
    click.secho(f"Deposit address not set or mnemonic is malformed.", fg="red")
    exit(1)

click.echo(f"Deposit address: {click.style(deposit_address, bold=True)}")
click.echo(f"Miner address: {click.style(miner_address, bold=True)}")

with open("./abi.json") as f:
    contract = algosdk.abi.Contract.from_json(f.read())


def get_client(network):
    if network == "mainnet":
        return algosdk.v2client.algod.AlgodClient(
            os.getenv("ALGOD_MAINNET_TOKEN"),
            f'{os.getenv("ALGOD_MAINNET_SERVER")}:{os.getenv("ALGOD_MAINNET_PORT")}',
        )
    else:
        return algosdk.v2client.algod.AlgodClient(
            os.getenv("ALGOD_TESTNET_TOKEN"),
            f'{os.getenv("ALGOD_TESTNET_SERVER")}:{os.getenv("ALGOD_TESTNET_PORT")}',
        )


def check_node_connection(network):
    client = get_client(network)
    try:
        status = client.status()
        click.secho(
            f"Node connected successfully. Block {status['last-round']}",
            fg="green",
        )
    except Exception as e:
        click.secho(
            "Node connection failed. Please update your node connectivity settings.",
            fg="red",
        )
        exit()


def get_state_value(state, key):
    bkey = base64.b64encode(bytes(key, "utf-8")).decode()
    for kv in state:
        if kv["key"] == bkey:
            return kv["value"]
    return None


def get_state_number(state, key):
    return get_state_value(state, key)["uint"]


def get_state_address(state, key):
    value = get_state_value(state, key)
    return algosdk.encoding.encode_address(base64.b64decode(value["bytes"]))

def get_app_id(network):
    return os.getenv("APP_MAINNET" if network == "mainnet" else "APP_TESTNET")

def get_application_data(network):
    app_id = get_app_id(network)
    client = get_client(network)
    app_info = client.application_info(app_id)
    state = app_info["params"]["global-state"]
    return {
        "id": int(app_id),
        "asset": get_state_number(state, "token"),
        "block": get_state_number(state, "block"),
        "total_effort": get_state_number(state, "total_effort"),
        "total_transcations": get_state_number(state, "total_transactions"),
        "halving": get_state_number(state, "halving"),
        "halving_supply": get_state_number(state, "halving_supply"),
        "mined_supply": get_state_number(state, "mined_supply"),
        "miner_reward": get_state_number(state, "miner_reward"),
        "last_miner": get_state_address(state, "last_miner"),
        "last_miner_effort": get_state_number(state, "last_miner_effort"),
        "current_miner": get_state_address(state, "current_miner"),
        "current_miner_effort": get_state_number(state, "current_miner_effort"),
        "start_timestamp": get_state_number(state, "start_timestamp"),
    }


def find(array, condition):
    return next(iter([item for item in array if condition(item)]), None)


def find_miner_state(account_info, app_id):
    if "apps-local-state" in account_info:
        for app in account_info["apps-local-state"]:
            if int(app['id']) == int(app_id):
                return app['key-value']
    return None


def get_miner_data(network):
    app_id = get_app_id(network)
    client = get_client(network)
    miner_info = client.account_info(miner_address)
    deposit_info = client.account_info(deposit_address)
    local_state = find_miner_state(deposit_info, app_id)
    if not local_state:
        click.secho(f"Deposit address is not opted in.", fg="red")
        exit(1)
    return {
        "own_effort": get_state_number(local_state, "effort"),
        "available_balance": miner_info["amount"] - miner_info["min-balance"]
    }


def check_miner(network, tpm, fee):
    client = get_client(network)
    miner_info = client.account_info(miner_address)
    miner_balance = max(0, miner_info["amount"] - miner_info["min-balance"])
    if miner_balance > 1000000:
        cost = tpm * fee
        click.echo(
            f"Miner will send {tpm} transactions per minute with {fee / pow(10, 6)} fee ({cost / pow(10, 6)} ALGO cost per minute)."
        )
        click.echo(
            f"Miner will spend {click.style(miner_balance / pow(10, 6), bold=True)} ALGO"
        )
        miner_seconds = math.floor(miner_balance / (cost / 60))
        miner_hours = math.floor(miner_seconds / 3600)
        miner_minutes = math.floor((miner_seconds % 3600) / 60)
        duration = click.style(
            f"{miner_hours} {'hour' if miner_hours == 1 else 'hours'} and {miner_minutes} {'minute' if miner_minutes == 1 else 'minutes'}",
            bold=True,
        )
        click.echo(f"Miner will run for approximately {duration}")
    else:
        click.secho(
            f"Miner has low balance ({miner_balance / pow(10, 6)} ALGO), please fund before mining.",
            fg="red",
        )
        exit(1)





def check_deposit_opted_in(network):
    client = get_client(network)
    deposit_info = client.account_info(deposit_address)
    app_info = get_application_data(network)
    app_opted_in = any(
        [app["id"] == app_info["id"] for app in deposit_info["apps-local-state"]]
    ) if "apps-local-state" in deposit_info else False
    if not app_opted_in:
        if deposit_pk:
            click.echo("Trying to opt-in the deposit address into the application...")
            check_enough_balance_or_exit(client, deposit_address, 129500)
            # 128500 microalgos increase in minimum balance after opt-in into the application
            # plus 1000 microalgos for the opt-in transaction fee
            try:
                opt_in(client, app_info["id"], "app", deposit_address, deposit_pk)
                click.echo("Deposit address opted successfully into the application.")
            except Exception as e:
                click.secho(f"Error: {e}", fg="red")
                click.secho(f"Deposit address not opted into app {app_info['id']}.", fg="red")
                exit(1)
        else:
            click.secho(f"Deposit address not opted into app {app_info['id']}.", fg="red")
            exit(1)

    asset_data = find(
        deposit_info["assets"], lambda asset: asset["asset-id"] == app_info["asset"]
    )
    if not asset_data:
        if deposit_pk:
            click.echo("Trying to opt-in the deposit address into the asset...")
            check_enough_balance_or_exit(client, deposit_address, 101000)
            # 100000 microalgos increase in minimum balance after opt-in into the asset
            # plus 1000 microalgos for the opt-in transaction fee
            try:
                opt_in(client, app_info["asset"], "asset", deposit_address, deposit_pk)
                click.echo("Deposit address opted successfully into the asset.")
            except Exception as e:
                click.secho(f"Error: {e}", fg="red")
                click.secho(f"Deposit address not opted into asset {app_info['asset']}.", fg="red")
                exit(1)
        else:
            click.secho(f"Deposit address not opted into asset {app_info['asset']}.", fg="red")

def check_enough_balance_or_exit(client, address, amount_needed):
    """Check if the account has at least amount_needed microalgos in addition
       to the minimum balance. If not, print an error message and exit."""
    info = client.account_info(address)
    balance = max(0, info["amount"] - info["min-balance"])
    if info["amount"] == 0:
        amount_needed += 100000 # 100000 microalgos minimum balance increase for new accounts
    if amount_needed - balance > 0:
        click.secho(
                f"Deposit account has low balance ({info['amount'] / pow(10, 6)} ALGO), " +
                f"please fund with additional {(amount_needed - balance) / pow(10, 6)} ALGO",
                fg="red",
                )
        exit(1)

def send_mining_group(client, sp, app_info, amount, total_txs, finish):
    try:
        composer = AtomicTransactionComposer()
        for i in range(amount):
            txid = total_txs + i
            composer.add_method_call(
                app_info["id"],
                contract.get_method_by_name("mine"),
                miner_address,
                sp,
                miner_signer,
                [algosdk.encoding.decode_address(deposit_address)],
                accounts=[app_info["last_miner"], deposit_address],
                foreign_assets=[app_info["asset"]],
                note=txid.to_bytes(math.ceil(math.log2(txid + 1) / 8), "big"),
            )
        composer.execute(client, 5)
    except Exception as e:
        click.secho(f"Transactions failed: {e}", fg="red")
    finish(amount)


pending_txs = 0
mutex = Lock()
prev_block = ""


def finish_transactions(amount):
    global pending_txs
    with mutex:
        pending_txs -= amount


def log_mining_stats(network, app_info, miner_info, total_txs):
    global pending_txs, prev_block
    own_effort_pct = miner_info['own_effort'] / app_info['last_miner_effort'] * 100.0
    if prev_block != app_info["block"] and prev_block != "":
        click.echo()
    click.echo(
        f"[{datetime.now().strftime('%H:%M:%S')}] "
        + f"{click.style(network.upper(), fg='red' if network == 'testnet' else 'yellow', bold=True)}: "
        + f"Sent {total_txs} transactions, {pending_txs} pending, block {app_info['block']}, current effort: {app_info['current_miner_effort']}, last effort: {app_info['last_miner_effort']}, own effort: {miner_info['own_effort']} ({own_effort_pct:.1f}%)"
    )
    prev_block = app_info["block"]

MINIMUM_BALANCE_THRESHOLD = int(os.getenv("MINIMUM_BALANCE_THRESHOLD", 1000000))

def mine(network, tpm, fee):
    global pending_txs
    client = get_client(network)
    started = int(time.time())
    started = started - started % 60
    transactions_to_send = tpm
    tps = math.ceil(tpm / 30)
    app_info = get_application_data(network)
    sp = None
    loops = 0
    starttime = time.monotonic()
    total_txs = 0
    now = int(time.time())
    while now < (app_info["start_timestamp"]):
        click.echo(
            f"Waiting for mining to begin... {app_info['start_timestamp'] - now} seconds left"
        )
        time.sleep(5)
        now = int(time.time())
    click.echo("Mining starts...")
    while True:
        now = int(time.time())
        now = now - now % 60
        if started != now:
            transactions_to_send = tpm
            started = now
        app_info = get_application_data(network)
        miner_info = get_miner_data(network)
        log_mining_stats(network, app_info, miner_info, total_txs)
        if miner_info["available_balance"] < MINIMUM_BALANCE_THRESHOLD:
            click.secho("Miner has insufficient funds, stopping mining.", fg="red")
            exit(1)
        sp = client.suggested_params()
        sp.flat_fee = True
        sp.fee = fee
        total = min(tps, transactions_to_send)
        while total > 0:
            amount = min(16, total)
            task = Thread(
                target=send_mining_group,
                args=(client, sp, app_info, amount, total_txs, finish_transactions),
            )
            task.start()
            total -= amount
            total_txs += amount
            with mutex:
                pending_txs += amount
        transactions_to_send -= total
        loops += 1
        time.sleep(2.0 - ((time.monotonic() - starttime) % 2.0))



@click.command()
@click.option("--tpm", default=1, help="Transactions per minute.")
@click.option("--fee", default=2000, help="Fee per transaction (micro algos).")
@click.argument(
    "network", type=click.Choice(["testnet", "mainnet"], case_sensitive=False)
)
def main(network, tpm, fee):
    click.echo(
        f"Network: {click.style(network.upper(), fg='red' if network == 'testnet' else 'yellow', bold=True)}"
    )
    check_node_connection(network)
    check_deposit_opted_in(network)
    check_miner(network, tpm, fee)
    click.confirm("Do you want to continue?", abort=True)
    mine(network, tpm, fee)

def opt_in(client, app_or_asset_id, id_type, address, pk):
    """Opt-in the account defined by `address` and private key `pk` into the application or asset id.
       id_type must be "app" or "asset".
       The function can throw an exception, to be managed by the caller."""
    sp = client.suggested_params()
    if id_type == "app":
        txn = algosdk.transaction.ApplicationOptInTxn(
            sender=address, sp=sp, index=app_or_asset_id)
    elif id_type == "asset":
        txn = algosdk.transaction.AssetTransferTxn(
            sender=address, sp=sp, receiver=address, amt=0, index=app_or_asset_id)
    signed_txn = txn.sign(pk)
    txid = client.send_transaction(signed_txn)
    # Wait for the transaction to be confirmed
    confirmed_txn = algosdk.transaction.wait_for_confirmation(client, txid, 4)
    click.echo(f"Transaction confirmed in round {confirmed_txn['confirmed-round']}")

# TODO
def withdraw():
    pass


if __name__ == "__main__":
    main()
