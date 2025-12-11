# Acceso x402

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)](https://fastapi.tiangolo.com)
[![Solana](https://img.shields.io/badge/Solana-mainnet-purple)](https://solana.com)
[![USDC](https://img.shields.io/badge/USDC-SPL_Token-2775CA)](https://www.circle.com/en/usdc)
[![Protocol](https://img.shields.io/badge/protocol-x402-orange)](https://www.x402.org)

> **Solana Payment Protocol API** — Accept USDC payments via HTTP 402

---

## Overview

Acceso x402 is a payment facilitation API that enables developers to monetize any HTTP resource using USDC on Solana. One API integration to add micropayments to your application.

## Features

| Feature | Description |
|---------|-------------|
| 🔐 **Solana Mainnet** | Production-ready USDC payments |
| ⚡ **Instant Settlement** | ~400ms finality on Solana |
| 💰 **Zero Protocol Fees** | Only Solana tx fees (~$0.00001) |
| 🛠️ **Simple Integration** | 3 API calls to add payments |
| 🔄 **Gasless for Users** | Facilitator sponsors transaction fees |
| 📦 **Standards Compliant** | HTTP 402 Payment Required protocol |

---

## Quick Start

### Installation

```bash
git clone https://github.com/Acceso-dev/Acceso-x402.git
cd Acceso-x402
chmod +x run.sh
./run.sh
```

### Configuration

Create `.env` from template:

```bash
cp .env.example .env
```

Required environment variables:

```env
FACILITATOR_PRIVATE_KEY=your_base58_private_key
SOLANA_RPC_URL=your_rpc_endpoint
```

### Run Server

```bash
./run.sh
# Server starts at http://localhost:8402
```

---

## API Reference

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/v1/x402/supported` | Supported schemes & networks |
| `POST` | `/v1/x402/requirements` | Generate payment requirements |
| `POST` | `/v1/x402/verify` | Verify payment header |
| `POST` | `/v1/x402/settle` | Settle payment on-chain |
| `GET` | `/v1/x402/fee-payer` | Get facilitator public key |
| `GET` | `/v1/x402/demo/protected` | Demo protected endpoint |

### Usage Example

```python
import requests

API_URL = "https://your-x402-api.com"

# 1. Generate payment requirements
resp = requests.post(f"{API_URL}/v1/x402/requirements", json={
    "price": "0.01",
    "payTo": "YourWalletAddress",
    "resource": "https://your-api.com/premium"
})
requirements = resp.json()["paymentRequired"]

# 2. Verify payment (when client sends X-PAYMENT header)
verify = requests.post(f"{API_URL}/v1/x402/verify", json={
    "paymentHeader": x_payment_header,
    "paymentRequirements": requirements["accepts"][0]
})

# 3. Settle on-chain
if verify.json()["isValid"]:
    settle = requests.post(f"{API_URL}/v1/x402/settle", json={
        "paymentHeader": x_payment_header,
        "paymentRequirements": requirements["accepts"][0]
    })
    tx_hash = settle.json()["txHash"]
```

---

## Protocol Flow

```
┌──────────┐          ┌──────────┐          ┌──────────┐          ┌──────────┐
│  Client  │          │ Your API │          │  x402    │          │  Solana  │
└────┬─────┘          └────┬─────┘          └────┬─────┘          └────┬─────┘
     │                     │                     │                     │
     │ 1. GET /resource    │                     │                     │
     │────────────────────>│                     │                     │
     │                     │                     │                     │
     │ 2. 402 + Payment    │                     │                     │
     │    Requirements     │                     │                     │
     │<────────────────────│                     │                     │
     │                     │                     │                     │
     │ 3. Sign Transaction │                     │                     │
     │    (User Wallet)    │                     │                     │
     │                     │                     │                     │
     │ 4. GET /resource    │                     │                     │
     │    + X-PAYMENT      │                     │                     │
     │────────────────────>│                     │                     │
     │                     │                     │                     │
     │                     │ 5. POST /verify     │                     │
     │                     │────────────────────>│                     │
     │                     │                     │                     │
     │                     │ 6. { isValid: true }│                     │
     │                     │<────────────────────│                     │
     │                     │                     │                     │
     │                     │ 7. POST /settle     │                     │
     │                     │────────────────────>│                     │
     │                     │                     │                     │
     │                     │                     │ 8. Submit TX        │
     │                     │                     │────────────────────>│
     │                     │                     │                     │
     │                     │                     │ 9. Confirmed        │
     │                     │                     │<────────────────────│
     │                     │                     │                     │
     │                     │ 10. { txHash }      │                     │
     │                     │<────────────────────│                     │
     │                     │                     │                     │
     │ 11. 200 + Content   │                     │                     │
     │<────────────────────│                     │                     │
     │                     │                     │                     │
```

---

## Configuration Reference

| Variable | Description | Default |
|----------|-------------|---------|
| `FACILITATOR_PRIVATE_KEY` | Fee payer keypair (base58) | **Required** |
| `SOLANA_RPC_URL` | Solana RPC endpoint | `https://api.mainnet-beta.solana.com` |
| `SOLANA_NETWORK` | Network identifier | `mainnet-beta` |
| `USDC_MINT` | USDC token address | `EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v` |
| `PORT` | API server port | `8402` |
| `LOG_LEVEL` | Logging verbosity | `INFO` |

---

## Facilitator Setup

The facilitator wallet sponsors Solana transaction fees for users (~$0.00001 per tx).

```bash
# 1. Generate keypair
solana-keygen new --outfile facilitator.json

# 2. Extract base58 private key
cat facilitator.json | python3 -c "import sys,json,base58; print(base58.b58encode(bytes(json.load(sys.stdin))).decode())"

# 3. Fund with SOL (~0.1 SOL ≈ 10,000 transactions)

# 4. Add to .env
echo "FACILITATOR_PRIVATE_KEY=your_key" >> .env
```

---

## Tech Stack

- **Runtime**: Python 3.10+
- **Framework**: FastAPI
- **Blockchain**: Solana (solana-py, solders)
- **Token**: USDC (SPL Token)

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

<p align="center">
  <b>Acceso x402</b> — Monetize anything with USDC
</p>
