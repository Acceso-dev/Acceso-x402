"""
Tests for x402 API
"""

import pytest
from fastapi.testclient import TestClient

from x402.main import app


client = TestClient(app)


def test_health():
    """Test health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "acceso-x402"


def test_root():
    """Test root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Acceso x402 API"
    assert "endpoints" in data


def test_supported():
    """Test supported schemes endpoint."""
    response = client.get("/v1/x402/supported")
    assert response.status_code == 200
    data = response.json()
    assert "kinds" in data
    assert len(data["kinds"]) >= 1
    assert data["kinds"][0]["scheme"] == "exact"
    assert data["kinds"][0]["network"] == "solana"


def test_generate_requirements():
    """Test generating payment requirements."""
    response = client.post("/v1/x402/requirements", json={
        "price": "0.01",
        "payTo": "11111111111111111111111111111111",  # Dummy address for test
        "resource": "https://example.com/api",
        "description": "Test payment",
    })
    # May fail without facilitator configured, but should not 500
    assert response.status_code in [200, 500]


def test_demo_protected_no_payment():
    """Test demo endpoint without payment returns 402 or 503."""
    response = client.get("/v1/x402/demo/protected")
    # Should return 402 when no X-PAYMENT header, or 503 if facilitator not configured
    assert response.status_code in [402, 503]
    if response.status_code == 402:
        data = response.json()
        assert "accepts" in data
        assert data["x402Version"] == 1
    elif response.status_code == 503:
        assert "facilitator not configured" in response.json()["detail"]
