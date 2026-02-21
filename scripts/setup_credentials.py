#!/usr/bin/env python3
"""Derive Polymarket CLOB API credentials from a Polygon wallet private key.

Usage:
    1. Set POLY_PRIVATE_KEY in your .env file
    2. Run: python scripts/setup_credentials.py
    3. The script will derive and print API credentials to add to .env
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def main() -> None:
    # Load .env if present
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        from dotenv import load_dotenv

        load_dotenv(env_file)

    private_key = os.getenv("POLY_PRIVATE_KEY")
    if not private_key:
        print("Error: POLY_PRIVATE_KEY not found in .env or environment")
        print("Set it first: echo 'POLY_PRIVATE_KEY=0xYOUR_KEY' >> .env")
        sys.exit(1)

    try:
        from py_clob_client.client import ClobClient
    except ImportError:
        print("Error: py-clob-client not installed")
        print("Install: pip install py-clob-client")
        sys.exit(1)

    from src.config import CHAIN_ID, CLOB_API_BASE

    print("Deriving API credentials from private key...")
    print(f"  CLOB API: {CLOB_API_BASE}")
    print(f"  Chain ID: {CHAIN_ID}")
    print()

    try:
        client = ClobClient(
            CLOB_API_BASE,
            key=private_key,
            chain_id=CHAIN_ID,
        )

        # Derive API credentials
        creds = client.derive_api_key()

        api_key = creds.get("apiKey", "")
        api_secret = creds.get("secret", "")
        api_passphrase = creds.get("passphrase", "")

        if not api_key:
            print("Error: Failed to derive API credentials")
            print("Response:", creds)
            sys.exit(1)

        print("API credentials derived successfully!")
        print()
        print("Add these to your .env file:")
        print("=" * 50)
        print(f"POLY_API_KEY={api_key}")
        print(f"POLY_API_SECRET={api_secret}")
        print(f"POLY_API_PASSPHRASE={api_passphrase}")
        print("=" * 50)
        print()

        # Optionally write to .env
        answer = input("Write to .env automatically? [y/N]: ").strip().lower()
        if answer == "y":
            lines = []
            if env_file.exists():
                lines = env_file.read_text().splitlines()

            # Update or append each credential
            for key, value in [
                ("POLY_API_KEY", api_key),
                ("POLY_API_SECRET", api_secret),
                ("POLY_API_PASSPHRASE", api_passphrase),
            ]:
                found = False
                for i, line in enumerate(lines):
                    if line.startswith(f"{key}="):
                        lines[i] = f"{key}={value}"
                        found = True
                        break
                if not found:
                    lines.append(f"{key}={value}")

            env_file.write_text("\n".join(lines) + "\n")
            print(f"Credentials written to {env_file}")

    except Exception as exc:
        print(f"Error deriving credentials: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
