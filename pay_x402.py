#!/usr/bin/env python3
"""
Real x402 Mainnet Payment Script
Pay 0.01 USDC to access protected endpoint
"""
import asyncio
import base64
import json
import sys
from pathlib import Path

import httpx
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import Transaction
from solders.message import Message
from solders.instruction import Instruction, AccountMeta
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price
from solana.rpc.async_api import AsyncClient
import struct

# Constants
TOKEN_PROGRAM_ID = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
ASSOCIATED_TOKEN_PROGRAM_ID = Pubkey.from_string("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")
USDC_MINT = Pubkey.from_string("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")

def get_associated_token_address(mint: Pubkey, owner: Pubkey) -> Pubkey:
    """Get associated token address."""
    seeds = [bytes(owner), bytes(TOKEN_PROGRAM_ID), bytes(mint)]
    return Pubkey.find_program_address(seeds, ASSOCIATED_TOKEN_PROGRAM_ID)[0]

def create_transfer_checked_instruction(source: Pubkey, mint: Pubkey, destination: Pubkey, owner: Pubkey, amount: int, decimals: int) -> Instruction:
    """Create TransferChecked instruction."""
    data = struct.pack("<BQB", 12, amount, decimals)
    keys = [
        AccountMeta(pubkey=source, is_signer=False, is_writable=True),
        AccountMeta(pubkey=mint, is_signer=False, is_writable=False),
        AccountMeta(pubkey=destination, is_signer=False, is_writable=True),
        AccountMeta(pubkey=owner, is_signer=True, is_writable=False),
    ]
    return Instruction(TOKEN_PROGRAM_ID, data, keys)

async def pay_x402(wallet_path: str, api_url: str = "http://localhost:8402"):
    print("=" * 80)
    print("x402 MAINNET PAYMENT")
    print("=" * 80)
    print()
    
    # Load wallet
    print(f"Loading wallet: {wallet_path}")
    try:
        with open(wallet_path, 'r') as f:
            data = json.load(f)
            if isinstance(data, list):
                wallet = Keypair.from_bytes(bytes(data[:64]))
            else:
                wallet = Keypair.from_bytes(base64.b64decode(data))
        print(f"✅ Wallet: {wallet.pubkey()}\n")
    except Exception as e:
        print(f"❌ Error loading wallet: {e}")
        return
    
    # Connect to Solana
    connection = AsyncClient("https://api.mainnet-beta.solana.com")
    
    try:
        # Check balances
        print("Checking balances...")
        sol_resp = await connection.get_balance(wallet.pubkey())
        sol_balance = sol_resp.value / 1e9
        print(f"SOL: {sol_balance:.4f}")
        
        user_usdc = get_associated_token_address(USDC_MINT, wallet.pubkey())
        try:
            usdc_resp = await connection.get_token_account_balance(user_usdc)
            usdc_balance = float(usdc_resp.value.amount) / 1e6
            print(f"USDC: {usdc_balance:.6f}")
            if usdc_balance < 0.01:
                print(f"\n❌ Need 0.01 USDC, have {usdc_balance}")
                return
        except:
            print("❌ USDC account not found")
            return
        
        print()
        
        # Get payment requirements
        print("STEP 1: Get Payment Requirements")
        print("-" * 80)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{api_url}/v1/x402/demo/protected")
            if resp.status_code != 402:
                print(f"❌ Expected 402, got {resp.status_code}")
                return
            
            reqs = resp.json()["accepts"][0]
            amount = int(reqs["maxAmountRequired"])
            pay_to = Pubkey.from_string(reqs["payTo"])
            fee_payer = Pubkey.from_string(reqs["extra"]["feePayer"])
            
            print(f"✅ Payment Required:")
            print(f"   Amount: {amount/1e6} USDC")
            print(f"   To: {pay_to}")
            print(f"   Fee Payer: {fee_payer}\n")
            
            # Build transaction
            print("STEP 2: Build & Sign Transaction")
            print("-" * 80)
            
            recipient_usdc = get_associated_token_address(USDC_MINT, pay_to)
            blockhash = (await connection.get_latest_blockhash()).value.blockhash
            
            instructions = [
                set_compute_unit_price(5),
                set_compute_unit_limit(200_000),
                create_transfer_checked_instruction(user_usdc, USDC_MINT, recipient_usdc, wallet.pubkey(), amount, 6),
            ]
            
            # Build message with fee_payer as first signer
            message = Message.new_with_blockhash(instructions, fee_payer, blockhash)
            
            # Create transaction and sign with customer
            # The message has 2 required signers: [fee_payer (pos 0), customer (pos 1)]
            # We sign for customer (pos 1), facilitator will sign for pos 0
            from solders.signature import Signature
            
            # Sign the message with customer wallet
            message_bytes = bytes(message)
            customer_sig = wallet.sign_message(message_bytes)
            
            # Build signatures array: [default for fee_payer, customer_sig]
            # Fee payer is position 0, customer is position 1
            num_signers = message.header.num_required_signatures
            signatures = [Signature.default()] * num_signers
            
            # Find customer position and place signature there
            for i, account_key in enumerate(message.account_keys[:num_signers]):
                if account_key == wallet.pubkey():
                    signatures[i] = customer_sig
                    print(f"   Customer signature at position {i}")
            
            # Create partially signed transaction
            tx = Transaction.populate(message, signatures)
            
            payment_proof = base64.b64encode(bytes(tx)).decode()
            print(f"✅ Transaction signed\n")
            
            # Submit payment
            print("STEP 3: Submit Payment")
            print("-" * 80)
            
            resp = await client.get(
                f"{api_url}/v1/x402/demo/protected",
                headers={"X-PAYMENT": payment_proof}
            )
            
            print(f"Status: {resp.status_code}")
            if resp.status_code == 200:
                print("\n" + "=" * 80)
                print("✅ PAYMENT SUCCESS!")
                print("=" * 80)
                result = resp.json()
                print(json.dumps(result, indent=2))
                if "signature" in result:
                    print(f"\nView on Solscan:")
                    print(f"https://solscan.io/tx/{result['signature']}")
            else:
                print(f"\n❌ Payment failed")
                print(json.dumps(resp.json(), indent=2))
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await connection.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python pay_x402.py <wallet_keypair.json>")
        sys.exit(1)
    
    wallet_path = sys.argv[1]
    if not Path(wallet_path).exists():
        print(f"❌ Wallet not found: {wallet_path}")
        sys.exit(1)
    
    asyncio.run(pay_x402(wallet_path))
