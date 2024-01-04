# Command Line Interface for mining Orange

Python & Pip are required for this CLI to work.

Fill out **MINER_MNEMONIC** and **DEPOSIT_ADDRESS** fields in `.env` (**DEPOSIT_MNEMONIC** is optional, only if you want to opt in through the CLI).

Install requirements:

`pip install -r requirements.txt`

To start mining, use the CLI like this:

`python main.py testnet --tpm 60 --fee 2000`

```
tpm - transactions per minute
fee - fee per transaction in micro ALGO
```