import os
from algosdk import mnemonic, account
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def generate_key_from_mnemonic(mnemonic_phrase):
    """Generate Algorand account address and private key from a mnemonic phrase."""
    private_key = mnemonic.to_private_key(mnemonic_phrase)
    address = account.address_from_private_key(private_key)
    return address, private_key

def main():
    # Get mnemonic from environment variable
    alg_mnemonic = os.getenv("MINER_MNEMONIC")

    if alg_mnemonic is None:
        print("Mnemonic not found in environment variables.")
        return

    # Generate account address and private key
    address, private_key = generate_key_from_mnemonic(alg_mnemonic)
    print(f"Address: {address}")
    print(f"Private Key: {private_key}")

if __name__ == "__main__":
    main()
