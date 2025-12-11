"""
x402 Protocol Types for Solana
Based on: https://github.com/coinbase/x402/blob/main/specs/schemes/exact/scheme_exact_svm.md
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Any
from enum import Enum


class Scheme(str, Enum):
    """Supported payment schemes."""
    EXACT = "exact"


class Network(str, Enum):
    """Supported networks."""
    SOLANA = "solana"
    SOLANA_DEVNET = "solana-devnet"


# ==============================================
# Payment Requirements (Server → Client)
# ==============================================

class PaymentRequirementsExtra(BaseModel):
    """Extra fields for Solana payment requirements."""
    fee_payer: str = Field(..., alias="feePayer", description="Public key of fee payer (facilitator)")
    
    class Config:
        populate_by_name = True


class PaymentRequirements(BaseModel):
    """Payment requirements returned in 402 response."""
    scheme: str = Field(default="exact")
    network: str = Field(default="solana")
    max_amount_required: str = Field(..., alias="maxAmountRequired", description="Amount in atomic units (USDC has 6 decimals)")
    asset: str = Field(..., description="Token mint address")
    pay_to: str = Field(..., alias="payTo", description="Merchant wallet address")
    resource: str = Field(..., description="URL of the resource being paid for")
    description: str = Field(default="", description="Human-readable description")
    mime_type: str = Field(default="application/json", alias="mimeType")
    max_timeout_seconds: int = Field(default=60, alias="maxTimeoutSeconds")
    output_schema: Optional[Any] = Field(default=None, alias="outputSchema")
    extra: PaymentRequirementsExtra
    
    class Config:
        populate_by_name = True


class PaymentRequiredResponse(BaseModel):
    """Full 402 response body."""
    x402_version: int = Field(default=1, alias="x402Version")
    accepts: List[PaymentRequirements]
    error: str = Field(default="")
    
    class Config:
        populate_by_name = True


# ==============================================
# Payment Payload (Client → Server)
# ==============================================

class PaymentPayloadData(BaseModel):
    """Payload data containing the partially-signed transaction."""
    transaction: str = Field(..., description="Base64-encoded partially-signed Solana transaction")


class PaymentPayload(BaseModel):
    """X-PAYMENT header payload (decoded from base64)."""
    x402_version: int = Field(default=1, alias="x402Version")
    scheme: str = Field(default="exact")
    network: str = Field(default="solana")
    payload: PaymentPayloadData
    
    class Config:
        populate_by_name = True


# ==============================================
# Facilitator API Types
# ==============================================

class VerifyRequest(BaseModel):
    """Request to verify a payment."""
    x402_version: int = Field(default=1, alias="x402Version")
    payment_header: str = Field(..., alias="paymentHeader", description="Base64-encoded X-PAYMENT header")
    payment_requirements: PaymentRequirements = Field(..., alias="paymentRequirements")
    
    class Config:
        populate_by_name = True


class VerifyResponse(BaseModel):
    """Response from payment verification."""
    is_valid: bool = Field(..., alias="isValid")
    invalid_reason: Optional[str] = Field(default=None, alias="invalidReason")
    
    class Config:
        populate_by_name = True


class SettleRequest(BaseModel):
    """Request to settle a payment on-chain."""
    x402_version: int = Field(default=1, alias="x402Version")
    payment_header: str = Field(..., alias="paymentHeader")
    payment_requirements: PaymentRequirements = Field(..., alias="paymentRequirements")
    
    class Config:
        populate_by_name = True


class SettleResponse(BaseModel):
    """Response from payment settlement."""
    success: bool
    error: Optional[str] = None
    tx_hash: Optional[str] = Field(default=None, alias="txHash")
    network: Optional[str] = None
    payer: Optional[str] = None
    
    class Config:
        populate_by_name = True


class SupportedKind(BaseModel):
    """Supported scheme/network pair."""
    scheme: str
    network: str


class SupportedResponse(BaseModel):
    """Response listing supported payment kinds."""
    kinds: List[SupportedKind]


# ==============================================
# API Request/Response Types
# ==============================================

class GenerateRequirementsRequest(BaseModel):
    """Request to generate payment requirements."""
    price: str = Field(..., description="Price in USD (e.g., '0.01' for 1 cent)")
    pay_to: str = Field(..., alias="payTo", description="Merchant wallet address to receive payment")
    resource: str = Field(..., description="URL of the protected resource")
    description: str = Field(default="API access payment")
    timeout_seconds: int = Field(default=60, alias="timeoutSeconds")
    
    class Config:
        populate_by_name = True


class GenerateRequirementsResponse(BaseModel):
    """Response with generated payment requirements."""
    payment_required: PaymentRequiredResponse = Field(..., alias="paymentRequired")
    
    class Config:
        populate_by_name = True
