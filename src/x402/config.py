"""
x402 Configuration
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Server
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8402)
    debug: bool = Field(default=False)
    
    # Solana Network
    solana_network: str = Field(default="mainnet-beta")
    solana_rpc_url: str = Field(default="https://api.mainnet-beta.solana.com")
    
    # USDC Token (Mainnet)
    usdc_mint: str = Field(default="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
    usdc_decimals: int = Field(default=6)
    
    # Facilitator (Fee Payer)
    facilitator_private_key: str = Field(default="")
    
    # Settings
    default_timeout_seconds: int = Field(default=60)
    max_compute_unit_price: int = Field(default=5)
    
    # Logging
    log_level: str = Field(default="INFO")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # Ignore extra environment variables


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
