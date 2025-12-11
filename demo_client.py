#!/usr/bin/env python3
"""
x402 Payment Demo Client

This script demonstrates the complete x402 payment flow:
1. Request protected endpoint → Get 402 with payment requirements
2. Construct and sign Solana transaction
3. Submit payment proof → Get protected content

Usage:
    python demo_client.py --wallet <path_to_keypair.json>
"""

import argparse
import base64
import json
import sys
from pathlib import Path

import httpx
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import Transaction
from solders.instruction import Instruction, AccountMeta
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price
from solders.system_program import ID as SYSTEM_PROGRAM_ID
from solana.rpc.async_api import AsyncClient
import asyncio


# USDC Token Program
TOKEN_PROGRAM_ID = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
USDC_MINT = Pubkey.from_string("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")


async def demo_payment_flow(wallet_path: str, api_url: str = "http://localhost:8402"):
    """Run the complete x402 payment demo."""
    
    print("=" * 70)
    print("x402 Payment Demo - Solana USDC Payment Protocol")
    print("=" * 70)
    print()
    
    # Load wallet
    print(f"📁 Loading wallet from: {wallet_path}")
    try:
        with open(wallet_path, 'r') as f:
            keypair_data = json.load(f)
            if isinstance(keypair_data, list):
                keypair_bytes = bytes(keypair_data[:64])
            else:
                keypair_bytes = bytes.fromhex(keypair_data)
            wallet = Keypair.from_bytes(keypair_bytes)
        print(f"✅ Wallet loaded: {wallet.pubkey()}")
        print()
    except Exception as e:
        print(f"❌ Failed to load wallet: {e}")
        return
    
    # Step 1: Request protected endpoint without payment
    print("Step 1: Request Protected Endpoint (No Payment)")
    print("-" * 70)
    print(f"GET {api_url}/v1/x402/demo/protected")
    print()
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{api_url}/v1/x402/demo/protected")
            print(f"Status: {response.status_code}")
            
            if response.status_code == 402:
                print("✅ Received 402 Payment Required")
                payment_req = response.json()
                print(json.dumps(payment_req, indent=2))
                print()
                
                # Extract payment requirements
                accepts = payment_req.get("accepts", [])
                if not accepts:
                    print("❌ No payment requirements found")
                    return
                
                requirements = accepts[0]
                amount = int(requirements.get("maxAmountRequired", "0"))
                pay_to = requirements.get("payTo")
                fee_payer = requirements.get("extra", {}).get("feePayer")
                
                print(f"💰 Payment Required:")
                print(f"   Amount: {amount} atomic units = {amount/1_000_000} USDC")
                print(f"   Pay To: {pay_to}")
                print(f"   Fee Payer: {fee_payer}")
                print()
                
            elif response.status_code == 503:
                print("❌ Service unavailable - Facilitator not configured")
                print(response.json())
                return
            else:
                print(f"❌ Unexpected status code: {response.status_code}")
                return
            
            # Step 2: Construct Partial Transaction
            print("Step 2: Construct Solana Transaction")
            print("-" * 70)
            print("Building transaction with:")
            print(f"  - ComputeBudget instructions")
            print(f"  - TransferChecked: {amount/1_000_000} USDC")
            print(f"  - From: {wallet.pubkey()}")
            print(f"  - To: {pay_to}")
            print()
            
            # For demo purposes, we'll simulate the transaction structure
            # In production, you'd use actual SPL Token transfer
            print("⚠️  DEMO MODE: Transaction construction simulated")
            print("   Real implementation requires:")
            print("   1. User's USDC token account")
            print("   2. SPL Token TransferChecked instruction")
            print("   3. User signature")
            print("   4. Facilitator signature (added by server)")
            print()
            
            # Simulate payment payload (base64 encoded transaction)
            demo_payment = base64.b64encode(b"DEMO_SIGNED_TRANSACTION").decode()
            
            # Step 3: Submit payment proof
            print("Step 3: Submit Payment Proof")
            print("-" * 70)
            print(f"GET {api_url}/v1/x402/demo/protected")
            print(f"Headers: X-PAYMENT: {demo_payment[:50]}...")
            print()
            
            response = await client.get(
                f"{api_url}/v1/x402/demo/protected",
                headers={"X-PAYMENT": demo_payment}
            )
            
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                print("✅ Payment Accepted - Access Granted!")
                content = response.json()
                print(json.dumps(content, indent=2))
            elif response.status_code == 402:
                print("❌ Payment verification failed")
                print(response.json())
            else:
                print(f"❌ Error: {response.status_code}")
                print(response.text)
            
            print()
            print("=" * 70)
            print("Demo Complete!")
            print()
            print("📝 Note: This demo uses simulated transactions.")
            print("   For real payments, implement:")
            print("   - Solana wallet integration")
            print("   - SPL Token account lookup")
            print("   - Proper transaction signing")
            print("   - Transaction submission to Solana RPC")
            print("=" * 70)
            
        except httpx.ConnectError:
            print(f"❌ Failed to connect to {api_url}")
            print("   Make sure the x402 server is running:")
            print("   cd /Users/apple/Documents/api/acceso-x402")
            print("   ./run.sh")
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="x402 Payment Demo Client - Solana USDC Payment Protocol"
    )
    parser.add_argument(
        "--wallet",
        type=str,
        help="Path to Solana wallet keypair JSON file",
        default=None,
    )
    parser.add_argument(
        "--api-url",
        type=str,
        default="http://localhost:8402",
        help="x402 API base URL (default: http://localhost:8402)",
    )
    
    args = parser.parse_args()
    
    # If no wallet provided, create a demo wallet
    if not args.wallet:
        print("⚠️  No wallet provided, generating demo wallet...")
        print()
        demo_wallet = Keypair()
        wallet_path = "/tmp/demo_wallet.json"
        with open(wallet_path, 'w') as f:
            json.dump(list(bytes(demo_wallet)), f)
        print(f"Demo wallet created: {wallet_path}")
        print(f"Public Key: {demo_wallet.pubkey()}")
        print()
        args.wallet = wallet_path
    
    # Run async demo
    asyncio.run(demo_payment_flow(args.wallet, args.api_url))


if __name__ == "__main__":
    main()
