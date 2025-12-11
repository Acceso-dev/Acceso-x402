"""
Acceso x402 - Solana Payment Protocol API

FastAPI application providing x402 payment services for Solana mainnet.
Developers can use this API to add USDC payments to their applications.
"""

import base64
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import structlog

from .config import get_settings
from .types import (
    PaymentRequirements,
    PaymentRequirementsExtra,
    PaymentRequiredResponse,
    VerifyRequest,
    VerifyResponse,
    SettleRequest,
    SettleResponse,
    SupportedResponse,
    SupportedKind,
    GenerateRequirementsRequest,
    GenerateRequirementsResponse,
)
from .facilitator import get_facilitator, close_facilitator

logger = structlog.get_logger()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting Acceso x402 API", port=settings.port)
    
    # Try to initialize facilitator (optional for development)
    try:
        facilitator = await get_facilitator()
        fee_payer = facilitator.get_fee_payer_pubkey()
        logger.info("Facilitator ready", fee_payer=fee_payer)
    except ValueError as e:
        logger.warning(
            "Facilitator not configured - some endpoints will be unavailable",
            error=str(e),
        )
    
    yield
    
    # Shutdown
    logger.info("Shutting down Acceso x402 API")
    await close_facilitator()


app = FastAPI(
    title="Acceso x402 API",
    description="Solana Payment Protocol - Accept USDC payments via HTTP 402",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==============================================
# Health & Info
# ==============================================

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "acceso-x402",
        "version": "1.0.0",
        "network": settings.solana_network,
    }


@app.get("/")
async def root():
    """API information."""
    return {
        "name": "Acceso x402 API",
        "description": "Solana Payment Protocol - Accept USDC payments via HTTP 402",
        "version": "1.0.0",
        "network": settings.solana_network,
        "usdc_mint": settings.usdc_mint,
        "docs": "/docs",
        "endpoints": {
            "generate": "POST /v1/x402/requirements",
            "verify": "POST /v1/x402/verify",
            "settle": "POST /v1/x402/settle",
            "supported": "GET /v1/x402/supported",
        },
    }


# ==============================================
# x402 API Endpoints
# ==============================================

@app.get("/v1/x402/supported", response_model=SupportedResponse)
async def get_supported():
    """
    Get supported payment schemes and networks.
    
    Returns the list of scheme/network pairs this facilitator supports.
    """
    return SupportedResponse(
        kinds=[
            SupportedKind(scheme="exact", network="solana"),
            SupportedKind(scheme="exact", network="solana-devnet"),
        ]
    )


@app.post("/v1/x402/requirements", response_model=GenerateRequirementsResponse)
async def generate_requirements(request: GenerateRequirementsRequest):
    """
    Generate payment requirements for a protected resource.
    
    Use this to create the 402 response body that you return to clients
    when they need to pay for access to your resource.
    
    Example:
    ```python
    # In your protected endpoint:
    response = requests.post("https://api.acceso.dev/v1/x402/requirements", json={
        "price": "0.01",  # $0.01 USD
        "payTo": "YourWalletAddress",
        "resource": "https://your-api.com/premium"
    })
    
    # Return 402 to client
    return Response(status_code=402, content=response.json()["paymentRequired"])
    ```
    """
    try:
        facilitator = await get_facilitator()
        
        # Convert USD price to USDC atomic units (6 decimals)
        price_usd = float(request.price.replace("$", ""))
        amount_atomic = int(price_usd * (10 ** settings.usdc_decimals))
        
        requirements = PaymentRequirements(
            scheme="exact",
            network=settings.solana_network.replace("-beta", ""),
            max_amount_required=str(amount_atomic),
            asset=settings.usdc_mint,
            pay_to=request.pay_to,
            resource=request.resource,
            description=request.description,
            mime_type="application/json",
            max_timeout_seconds=request.timeout_seconds,
            output_schema=None,
            extra=PaymentRequirementsExtra(fee_payer=facilitator.get_fee_payer_pubkey()),
        )
        
        payment_required = PaymentRequiredResponse(
            x402_version=1,
            accepts=[requirements],
            error="",
        )
        
        return GenerateRequirementsResponse(payment_required=payment_required)
        
    except Exception as e:
        logger.error("Failed to generate requirements", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/x402/verify", response_model=VerifyResponse)
async def verify_payment(request: VerifyRequest):
    """
    Verify a payment payload.
    
    Call this when you receive a request with an X-PAYMENT header.
    Returns whether the payment is valid before you grant access.
    
    Example:
    ```python
    # In your protected endpoint:
    payment_header = request.headers.get("X-PAYMENT")
    if not payment_header:
        return Response(status_code=402, ...)
    
    verify = requests.post("https://api.acceso.dev/v1/x402/verify", json={
        "paymentHeader": payment_header,
        "paymentRequirements": your_requirements
    })
    
    if verify.json()["isValid"]:
        # Grant access
        ...
    ```
    """
    try:
        facilitator = await get_facilitator()
        result = await facilitator.verify(
            request.payment_header,
            request.payment_requirements,
        )
        return result
        
    except Exception as e:
        logger.error("Verification failed", error=str(e))
        return VerifyResponse(is_valid=False, invalid_reason=str(e))


@app.post("/v1/x402/settle", response_model=SettleResponse)
async def settle_payment(request: SettleRequest):
    """
    Settle a payment on Solana.
    
    Call this after verifying the payment to submit it to the blockchain.
    Returns the transaction hash on success.
    
    Example:
    ```python
    # After verification succeeds:
    settle = requests.post("https://api.acceso.dev/v1/x402/settle", json={
        "paymentHeader": payment_header,
        "paymentRequirements": your_requirements
    })
    
    if settle.json()["success"]:
        tx_hash = settle.json()["txHash"]
        # Add X-PAYMENT-RESPONSE header to your response
        ...
    ```
    """
    try:
        facilitator = await get_facilitator()
        result = await facilitator.settle(
            request.payment_header,
            request.payment_requirements,
        )
        return result
        
    except Exception as e:
        logger.error("Settlement failed", error=str(e))
        return SettleResponse(success=False, error=str(e))


@app.get("/v1/x402/fee-payer")
async def get_fee_payer():
    """
    Get the facilitator's fee payer public key.
    
    This is the address that will pay transaction fees.
    Include this in your payment requirements as `extra.feePayer`.
    """
    try:
        facilitator = await get_facilitator()
        return {
            "feePayer": facilitator.get_fee_payer_pubkey(),
            "network": settings.solana_network,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==============================================
# Example Protected Endpoint (for testing)
# ==============================================

@app.get("/v1/x402/demo/protected")
async def demo_protected(
    request: Request,
    x_payment: Optional[str] = Header(None, alias="X-PAYMENT"),
):
    """
    Demo protected endpoint.
    
    Shows how x402 payment flow works:
    1. Request without X-PAYMENT → 402 with requirements
    2. Request with valid X-PAYMENT → 200 with content
    """
    facilitator = await get_facilitator()
    
    # Check if facilitator is configured
    try:
        fee_payer_pubkey = facilitator.get_fee_payer_pubkey()
    except ValueError:
        raise HTTPException(
            status_code=503,
            detail="Demo endpoint unavailable: facilitator not configured. Set FACILITATOR_KEYPAIR env var.",
        )
    
    # Payment requirements for this demo endpoint
    demo_requirements = PaymentRequirements(
        scheme="exact",
        network=settings.solana_network.replace("-beta", ""),
        max_amount_required=str(10000),  # 0.01 USDC (10,000 atomic units with 6 decimals)
        asset=settings.usdc_mint,
        pay_to=fee_payer_pubkey,  # Pay to facilitator for demo
        resource=str(request.url),
        description="Access to protected API endpoint - Real payment required: 0.01 USDC",
        mime_type="application/json",
        max_timeout_seconds=60,
        output_schema=None,
        extra=PaymentRequirementsExtra(feePayer=fee_payer_pubkey),
    )
    
    if not x_payment:
        # No payment - return 402
        return JSONResponse(
            status_code=402,
            content=PaymentRequiredResponse(
                x402_version=1,
                accepts=[demo_requirements],
                error="Payment required",
            ).model_dump(by_alias=True),
        )
    
    # Verify payment
    verify_result = await facilitator.verify(x_payment, demo_requirements)
    if not verify_result.is_valid:
        return JSONResponse(
            status_code=402,
            content=PaymentRequiredResponse(
                x402_version=1,
                accepts=[demo_requirements],
                error=verify_result.invalid_reason or "Invalid payment",
            ).model_dump(by_alias=True),
        )
    
    # Settle payment
    settle_result = await facilitator.settle(x_payment, demo_requirements)
    if not settle_result.success:
        return JSONResponse(
            status_code=402,
            content=PaymentRequiredResponse(
                x402_version=1,
                accepts=[demo_requirements],
                error=settle_result.error or "Settlement failed",
            ).model_dump(by_alias=True),
        )
    
    # Payment successful - return protected content
    response = JSONResponse(
        content={
            "message": "🎉 Payment successful! Here's your protected content.",
            "secret_data": "This is the premium content you paid for.",
            "tx_hash": settle_result.tx_hash,
        }
    )
    
    # Add payment response header
    payment_response = base64.b64encode(
        settle_result.model_dump_json(by_alias=True).encode()
    ).decode()
    response.headers["X-PAYMENT-RESPONSE"] = payment_response
    
    return response


# ==============================================
# Run with: uvicorn x402.main:app --reload
# ==============================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "x402.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
