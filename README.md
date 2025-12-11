# Acceso x402 - Solana Payment Protocol API

Accept USDC payments on Solana via HTTP 402. One API to monetize any resource.

## Features

- 🔐 **Solana Mainnet** - Production-ready USDC payments
- ⚡ **Instant Settlement** - 2-second finality on Solana
- 💰 **Zero Fees** - Protocol has no fees (only Solana tx fees ~$0.00001)
- 🛠️ **Simple Integration** - 3 API calls to add payments
- 🔄 **Gasless for Users** - Facilitator sponsors transaction fees

## Quick Start

### 1. Install & Run

```bash
cd acceso-x402
chmod +x run.sh
./run.sh
```

### 2. Configure `.env`

```bash
SOLANA_RPC_URL=https://mainnet.helius-rpc.com/?api-key=YOUR_KEY
FACILITATOR_PRIVATE_KEY=your_base58_private_key
```

### 3. Use the API

```python
import requests

# Generate payment requirements for your protected resource
resp = requests.post("http://localhost:8402/v1/x402/requirements", json={
    "price": "0.01",  # $0.01 USDC
    "payTo": "YourWalletAddress",
    "resource": "https://your-api.com/premium"
})
payment_required = resp.json()["paymentRequired"]

# Return 402 to clients who haven't paid
# When client pays, they send X-PAYMENT header

# Verify payment
verify = requests.post("http://localhost:8402/v1/x402/verify", json={
    "paymentHeader": client_x_payment_header,
    "paymentRequirements": payment_required["accepts"][0]
})

if verify.json()["isValid"]:
    # Settle on-chain
    settle = requests.post("http://localhost:8402/v1/x402/settle", json={
        "paymentHeader": client_x_payment_header,
        "paymentRequirements": payment_required["accepts"][0]
    })
    
    if settle.json()["success"]:
        print(f"Payment received! TX: {settle.json()['txHash']}")
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/v1/x402/supported` | List supported schemes/networks |
| `POST` | `/v1/x402/requirements` | Generate 402 payment requirements |
| `POST` | `/v1/x402/verify` | Verify X-PAYMENT header |
| `POST` | `/v1/x402/settle` | Settle payment on Solana |
| `GET` | `/v1/x402/fee-payer` | Get facilitator public key |
| `GET` | `/v1/x402/demo/protected` | Demo protected endpoint |

## Protocol Flow

```
1. Client → Your API: Request protected resource
2. Your API → Client: 402 + PaymentRequirements (from /requirements)
3. Client: Signs Solana transaction with their wallet
4. Client → Your API: Request with X-PAYMENT header
5. Your API → Acceso: POST /verify
6. Acceso → Your API: { isValid: true }
7. Your API → Acceso: POST /settle  
8. Acceso → Solana: Submit transaction
9. Acceso → Your API: { success: true, txHash: "..." }
10. Your API → Client: 200 + Content + X-PAYMENT-RESPONSE
```

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `SOLANA_RPC_URL` | Solana RPC endpoint | mainnet-beta |
| `USDC_MINT` | USDC token address | EPjFWdd5... |
| `FACILITATOR_PRIVATE_KEY` | Fee payer keypair (base58) | Required |
| `PORT` | API port | 8402 |

## Facilitator Setup

The facilitator pays Solana transaction fees (~0.00001 SOL per tx).

1. Generate a new keypair:
```bash
solana-keygen new --outfile facilitator.json
```

2. Get the base58 private key:
```bash
cat facilitator.json | python3 -c "import sys,json,base58; print(base58.b58encode(bytes(json.load(sys.stdin))).decode())"
```

3. Fund with SOL (~0.1 SOL = ~10,000 transactions)

4. Add to `.env`:
```bash
FACILITATOR_PRIVATE_KEY=your_base58_key
```

## License

MIT
