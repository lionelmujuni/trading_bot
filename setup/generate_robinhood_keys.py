"""
Robinhood API Key Setup Script
================================
Generates an Ed25519 keypair for Robinhood Crypto Trading API authentication.

Steps:
  1. Run this script:  python setup/generate_robinhood_keys.py
  2. Copy the PUBLIC KEY and paste it into Robinhood's credential form:
       https://robinhood.com/account/crypto  (web classic → API → Create Credential)
  3. Robinhood will display your API Key (format: rh-api-xxxxxxxx-...).
  4. Re-run this script with --api-key <your-api-key> to print your final .env block,
     OR paste the API key when prompted.

Requirements:
  pip install pynacl
"""

import base64
import sys
import os

try:
    import nacl.signing
except ImportError:
    print("ERROR: PyNaCl is not installed.")
    print("  Run:  pip install pynacl")
    sys.exit(1)


def generate_keypair() -> tuple[str, str]:
    """Generate a new Ed25519 keypair and return (private_b64, public_b64)."""
    private_key = nacl.signing.SigningKey.generate()
    public_key = private_key.verify_key

    private_b64 = base64.b64encode(private_key.encode()).decode()
    public_b64 = base64.b64encode(public_key.encode()).decode()
    return private_b64, public_b64


def print_separator(char: str = "─", width: int = 60) -> None:
    print(char * width)


def main() -> None:
    # Parse optional --api-key argument
    api_key_arg: str | None = None
    args = sys.argv[1:]
    if "--api-key" in args:
        idx = args.index("--api-key")
        if idx + 1 < len(args):
            api_key_arg = args[idx + 1]
        else:
            print("ERROR: --api-key flag requires a value.")
            sys.exit(1)

    print()
    print_separator("=")
    print("  Robinhood Crypto API — Key Generation")
    print_separator("=")

    private_b64, public_b64 = generate_keypair()

    print()
    print("STEP 1 — Public Key (paste this into Robinhood's website)")
    print_separator()
    print(public_b64)
    print_separator()
    print()
    print("  → Go to: https://robinhood.com/account/crypto")
    print("  → Click 'Create Credential'")
    print("  → Paste the PUBLIC KEY above into the key field")
    print("  → Robinhood will give you an API Key (rh-api-xxxxxxxx-...)")
    print()

    print("STEP 2 — Private Key (keep this secret — never share it)")
    print_separator()
    print(private_b64)
    print_separator()
    print()

    # Get API key from arg or prompt
    if api_key_arg:
        api_key = api_key_arg.strip()
    else:
        print("STEP 3 — Enter your Robinhood API Key from the website")
        print("         (press Enter to skip and add it manually later)")
        try:
            api_key = input("  API Key: ").strip()
        except (KeyboardInterrupt, EOFError):
            api_key = ""
            print()

    print()
    print_separator("=")
    print("  .env configuration block")
    print_separator("=")
    print()
    print("Add these lines to your .env file in the trading_bot directory:")
    print()
    print("  EXCHANGE=robinhood")
    if api_key:
        print(f"  API_KEY={api_key}")
    else:
        print("  API_KEY=<paste your rh-api-... key here>")
    print(f"  BASE64_PRIVATE_KEY={private_b64}")
    print()
    print_separator("=")
    print()
    print("WARNING: Never commit your .env file or private key to version control.")
    print("         Add .env to your .gitignore.")
    print()

    # Offer to write a .env.robinhood template file in setup/
    setup_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(setup_dir, ".env.robinhood.template")
    try:
        with open(template_path, "w") as f:
            f.write("# Robinhood Crypto API credentials\n")
            f.write("# Copy this file to ../.env and fill in missing values\n\n")
            f.write("EXCHANGE=robinhood\n")
            f.write(f"API_KEY={api_key if api_key else '<paste your rh-api-... key here>'}\n")
            f.write(f"BASE64_PRIVATE_KEY={private_b64}\n")
        print(f"Template saved to: {template_path}")
        print("Copy it to the trading_bot root as '.env' and fill in any missing values.")
    except OSError as e:
        print(f"(Could not write template file: {e})")

    print()


if __name__ == "__main__":
    main()
