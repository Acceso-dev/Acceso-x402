"""
x402 Solana Facilitator
Verifies and settles payments on Solana mainnet using USDC SPL token transfers.
"""

import base64
import base58
import json
import struct
from typing import Optional, Tuple

from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction
from solders.message import MessageV0
from solders.instruction import CompiledInstruction
import structlog

from .config import get_settings
from .types import (
    PaymentPayload,
    PaymentRequirements,
    VerifyResponse,
    SettleResponse,
)

logger = structlog.get_logger()

# Program IDs
COMPUTE_BUDGET_PROGRAM = Pubkey.from_string("ComputeBudget111111111111111111111111111111")
SPL_TOKEN_PROGRAM = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
TOKEN_2022_PROGRAM = Pubkey.from_string("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb")
ASSOCIATED_TOKEN_PROGRAM = Pubkey.from_string("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")


class SolanaFacilitator:
    """
    Solana x402 Facilitator
    
    Handles verification and settlement of x402 payments on Solana.
    Acts as fee payer (gas sponsor) for client transactions.
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.rpc_client: Optional[AsyncClient] = None
        self.fee_payer: Optional[Keypair] = None
        
    async def initialize(self):
        """Initialize RPC client and fee payer keypair."""
        self.rpc_client = AsyncClient(self.settings.solana_rpc_url)
        
        if self.settings.facilitator_private_key:
            try:
                # Decode base58 private key
                secret_key = base58.b58decode(self.settings.facilitator_private_key)
                self.fee_payer = Keypair.from_bytes(secret_key)
                logger.info(
                    "Facilitator initialized",
                    fee_payer=str(self.fee_payer.pubkey()),
                    network=self.settings.solana_network,
                )
            except Exception as e:
                logger.error("Failed to load facilitator keypair", error=str(e))
                raise ValueError(f"Invalid facilitator private key: {e}")
        else:
            logger.warning("No facilitator private key configured")
    
    async def close(self):
        """Close RPC client connection."""
        if self.rpc_client:
            await self.rpc_client.close()
    
    def get_fee_payer_pubkey(self) -> str:
        """Get the fee payer's public key."""
        if not self.fee_payer:
            raise ValueError("Facilitator not initialized")
        return str(self.fee_payer.pubkey())
    
    async def verify(
        self,
        payment_header: str,
        requirements: PaymentRequirements,
    ) -> VerifyResponse:
        """
        Verify a payment payload.
        
        Checks:
        1. Transaction has exactly 3 instructions (ComputeBudget x2 + TransferChecked)
        2. Fee payer is not in any instruction accounts
        3. Transfer amount matches requirements
        4. Transfer destination matches pay_to ATA
        """
        try:
            # Decode payment header - X-PAYMENT contains raw base64-encoded transaction
            tx_bytes = base64.b64decode(payment_header)
            
            # Try legacy transaction first
            try:
                from solders.transaction import Transaction as LegacyTransaction
                tx = LegacyTransaction.from_bytes(tx_bytes)
                message = tx.message
                instructions = message.instructions
                account_keys = message.account_keys
            except:
                # Try versioned transaction
                tx = VersionedTransaction.from_bytes(tx_bytes)
                message = tx.message
                if not isinstance(message, MessageV0):
                    return VerifyResponse(is_valid=False, invalid_reason="Unsupported transaction format")
                instructions = message.instructions
                account_keys = message.account_keys
            
            # Must have exactly 3 instructions
            if len(instructions) != 3:
                return VerifyResponse(
                    is_valid=False,
                    invalid_reason=f"Expected 3 instructions, got {len(instructions)}"
                )
            
            # First 2 instructions should be ComputeBudget (SetComputeUnitPrice and SetComputeUnitLimit in any order)
            compute_budget_count = 0
            price_instruction_idx = None
            
            for idx in [0, 1]:
                if self._is_compute_budget_instruction(instructions[idx], account_keys, 2):  # SetComputeUnitLimit
                    compute_budget_count += 1
                elif self._is_compute_budget_instruction(instructions[idx], account_keys, 3):  # SetComputeUnitPrice
                    compute_budget_count += 1
                    price_instruction_idx = idx
            
            if compute_budget_count != 2:
                return VerifyResponse(
                    is_valid=False,
                    invalid_reason="First 2 instructions must be ComputeBudget instructions"
                )
            
            # Verify compute unit price is reasonable
            if price_instruction_idx is not None:
                price_valid, price_reason = self._verify_compute_price(instructions[price_instruction_idx])
                if not price_valid:
                    return VerifyResponse(is_valid=False, invalid_reason=price_reason)
            
            # Instruction 3: TransferChecked
            transfer_valid, transfer_reason = await self._verify_transfer_instruction(
                instructions[2],
                account_keys,
                requirements,
            )
            if not transfer_valid:
                return VerifyResponse(is_valid=False, invalid_reason=transfer_reason)
            
            # Verify fee payer is not in any instruction accounts
            fee_payer_pubkey = Pubkey.from_string(requirements.extra.fee_payer)
            for ix in instructions:
                for account_idx in ix.accounts:
                    if account_keys[account_idx] == fee_payer_pubkey:
                        return VerifyResponse(
                            is_valid=False,
                            invalid_reason="Fee payer must not be in instruction accounts"
                        )
            
            logger.info("Payment verified successfully")
            return VerifyResponse(is_valid=True)
            
        except Exception as e:
            logger.error("Payment verification failed", error=str(e))
            return VerifyResponse(is_valid=False, invalid_reason=str(e))
    
    async def settle(
        self,
        payment_header: str,
        requirements: PaymentRequirements,
    ) -> SettleResponse:
        """
        Settle a payment on-chain.
        
        1. Decode the partially-signed transaction
        2. Add facilitator signature (fee payer)
        3. Submit to Solana network
        4. Return transaction hash
        """
        try:
            if not self.fee_payer:
                return SettleResponse(
                    success=False,
                    error="Facilitator not configured",
                )
            
            # First verify the payment
            verify_result = await self.verify(payment_header, requirements)
            if not verify_result.is_valid:
                return SettleResponse(
                    success=False,
                    error=f"Verification failed: {verify_result.invalid_reason}",
                )
            
            # Decode transaction - X-PAYMENT contains raw base64-encoded transaction
            tx_bytes = base64.b64decode(payment_header)
            
            # Try legacy transaction first
            try:
                from solders.transaction import Transaction as LegacyTransaction
                tx = LegacyTransaction.from_bytes(tx_bytes)
                is_legacy = True
            except Exception as e:
                logger.warning("Legacy transaction parse failed, trying versioned", error=str(e))
                # Try versioned transaction
                try:
                    tx = VersionedTransaction.from_bytes(tx_bytes)
                    is_legacy = False
                except Exception as e2:
                    return SettleResponse(
                        success=False,
                        error=f"Failed to parse transaction: {str(e2)}",
                    )
            
            # Get recent blockhash
            blockhash_resp = await self.rpc_client.get_latest_blockhash(commitment=Confirmed)
            recent_blockhash = blockhash_resp.value.blockhash
            
            if is_legacy:
                # For legacy transactions, we need to add facilitator signature
                # The customer already partially signed, so we just add our signature
                from solders.transaction import Transaction as LegacyTransaction
                from solders.signature import Signature
                
                # Get message bytes and sign with facilitator
                message = tx.message
                message_bytes = bytes(message)
                facilitator_sig = self.fee_payer.sign_message(message_bytes)
                
                # The message has num_required_signatures signers
                # Fee payer (facilitator) should be account[0]
                # Customer (sender) should be account[1]
                num_signers = message.header.num_required_signatures
                
                logger.debug(
                    "Transaction signatures debug",
                    num_signers=num_signers,
                    num_existing_sigs=len(tx.signatures),
                    account_keys=[str(k) for k in message.account_keys[:num_signers]],
                    fee_payer=str(self.fee_payer.pubkey()),
                )
                
                # Build signatures array - positions must match account_keys
                signatures = list(tx.signatures)  # Start with existing signatures
                
                # Find facilitator position and add signature there
                for i, account_key in enumerate(message.account_keys[:num_signers]):
                    if str(account_key) == str(self.fee_payer.pubkey()):
                        signatures[i] = facilitator_sig
                        logger.debug(f"Added facilitator signature at position {i}")
                
                # Create populated transaction with all signatures
                tx_to_send = LegacyTransaction.populate(message, signatures)
            else:
                # For versioned transactions
                message = tx.message
                all_signatures = list(tx.signatures) if hasattr(tx, 'signatures') else []
                # Add facilitator signature
                facilitator_sig = self.fee_payer.sign_message(
                    bytes(message.hash())
                )
                all_signatures.append(facilitator_sig)
                final_tx = VersionedTransaction.populate(message, all_signatures)
                tx_to_send = final_tx
            
            # Send transaction
            from solana.rpc.types import TxOpts
            result = await self.rpc_client.send_transaction(
                tx_to_send,
                opts=TxOpts(skip_preflight=False, preflight_commitment=Confirmed),
            )
            
            tx_signature = str(result.value)
            
            logger.info(
                "Payment settled",
                tx_hash=tx_signature,
                network=self.settings.solana_network,
            )
            
            return SettleResponse(
                success=True,
                tx_hash=tx_signature,
                network=self.settings.solana_network,
                payer=str(self.fee_payer.pubkey()),
            )
            
        except Exception as e:
            logger.error("Payment settlement failed", error=str(e))
            return SettleResponse(success=False, error=str(e))
    
    def _is_compute_budget_instruction(
        self,
        instruction: CompiledInstruction,
        account_keys: list,
        discriminator: int,
    ) -> bool:
        """Check if instruction is a ComputeBudget instruction with given discriminator."""
        program_id = account_keys[instruction.program_id_index]
        if program_id != COMPUTE_BUDGET_PROGRAM:
            return False
        
        if len(instruction.data) < 1:
            return False
        
        return instruction.data[0] == discriminator
    
    def _verify_compute_price(
        self,
        instruction: CompiledInstruction,
    ) -> Tuple[bool, Optional[str]]:
        """Verify compute unit price is within limits."""
        if len(instruction.data) < 9:
            return False, "Invalid SetComputeUnitPrice instruction"
        
        # Data format: [discriminator (1 byte), price (8 bytes little endian)]
        price = struct.unpack("<Q", instruction.data[1:9])[0]
        
        max_price = self.settings.max_compute_unit_price
        if price > max_price:
            return False, f"Compute unit price {price} exceeds max {max_price}"
        
        return True, None
    
    async def _verify_transfer_instruction(
        self,
        instruction: CompiledInstruction,
        account_keys: list,
        requirements: PaymentRequirements,
    ) -> Tuple[bool, Optional[str]]:
        """Verify TransferChecked instruction matches requirements."""
        program_id = account_keys[instruction.program_id_index]
        
        # Must be SPL Token or Token-2022
        if program_id not in [SPL_TOKEN_PROGRAM, TOKEN_2022_PROGRAM]:
            return False, "Third instruction must be SPL Token TransferChecked"
        
        # TransferChecked discriminator is 12
        if len(instruction.data) < 1 or instruction.data[0] != 12:
            return False, "Expected TransferChecked instruction"
        
        # Parse TransferChecked data: [discriminator (1), amount (8), decimals (1)]
        if len(instruction.data) < 10:
            return False, "Invalid TransferChecked data"
        
        amount = struct.unpack("<Q", instruction.data[1:9])[0]
        decimals = instruction.data[9]
        
        # Verify amount matches
        required_amount = int(requirements.max_amount_required)
        if amount != required_amount:
            return False, f"Amount {amount} does not match required {required_amount}"
        
        # Verify decimals match USDC
        if decimals != self.settings.usdc_decimals:
            return False, f"Decimals {decimals} does not match expected {self.settings.usdc_decimals}"
        
        # TransferChecked accounts: [source, mint, destination, authority]
        if len(instruction.accounts) < 4:
            return False, "TransferChecked requires 4 accounts"
        
        # Verify mint matches
        mint = account_keys[instruction.accounts[1]]
        expected_mint = Pubkey.from_string(requirements.asset)
        if mint != expected_mint:
            return False, f"Mint {mint} does not match required {expected_mint}"
        
        # Verify destination is correct ATA for pay_to
        destination = account_keys[instruction.accounts[2]]
        pay_to = Pubkey.from_string(requirements.pay_to)
        expected_ata = self._get_associated_token_address(pay_to, expected_mint, program_id)
        
        if destination != expected_ata:
            return False, f"Destination {destination} does not match expected ATA {expected_ata}"
        
        return True, None
    
    def _get_associated_token_address(
        self,
        owner: Pubkey,
        mint: Pubkey,
        token_program: Pubkey,
    ) -> Pubkey:
        """Derive associated token address."""
        seeds = [
            bytes(owner),
            bytes(token_program),
            bytes(mint),
        ]
        ata, _ = Pubkey.find_program_address(seeds, ASSOCIATED_TOKEN_PROGRAM)
        return ata


# Global facilitator instance
_facilitator: Optional[SolanaFacilitator] = None


async def get_facilitator() -> SolanaFacilitator:
    """Get or create the global facilitator instance."""
    global _facilitator
    if _facilitator is None:
        _facilitator = SolanaFacilitator()
        await _facilitator.initialize()
    return _facilitator


async def close_facilitator():
    """Close the global facilitator instance."""
    global _facilitator
    if _facilitator:
        await _facilitator.close()
        _facilitator = None
