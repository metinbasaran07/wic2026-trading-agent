"""Central configuration settings for the trading workstation."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # =========================================================================
    # Application Mode
    # =========================================================================
    MODE: Literal["dev", "trial", "live"] = "dev"
    """Operating mode: dev (development), trial (competition trial), live (competition live)"""

    # =========================================================================
    # Interactive Brokers Connection
    # =========================================================================
    IB_HOST: str = "127.0.0.1"
    """IB Gateway/TWS host"""

    IB_PORT: int = 4002
    """IB Gateway/TWS port (4001=live, 4002=paper, 7496=TWS live, 7497=TWS paper)"""

    IB_CLIENT_ID: int = 1
    """Unique client ID for this connection"""

    IB_READONLY: bool = False
    """Read-only mode (no order placement)"""

    IB_TIMEOUT: int = 30
    """Connection timeout in seconds"""

    # =========================================================================
    # Market Data
    # =========================================================================
    MARKET_DATA_DELAY_MINUTES: int = 15
    """Market data delay (competition uses 15-min delayed data)"""

    DEFAULT_TIMEFRAME: str = "15 mins"
    """Default bar timeframe for strategy"""

    LOOKBACK_DAYS: int = 30
    """Historical data lookback for initialization"""

    # =========================================================================
    # LLM Providers
    # =========================================================================
    LLM_PROVIDER: Literal[
        "openrouter", "anthropic", "openai", "azure", "gemini", "ollama", "team_key", "mock"
    ] = "openrouter"
    """LLM provider to use"""

    # --- OpenRouter ---
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_MODEL: str = "anthropic/claude-3.5-sonnet"
    OPENROUTER_MAX_TOKENS: int = 4096
    OPENROUTER_TEMPERATURE: float = 0.1

    # --- Anthropic (Direct) ---
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-3-5-sonnet-20241022"
    ANTHROPIC_MAX_TOKENS: int = 4096
    ANTHROPIC_TEMPERATURE: float = 0.1

    # --- OpenAI (Direct) ---
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-4o"
    OPENAI_MAX_TOKENS: int = 4096
    OPENAI_TEMPERATURE: float = 0.1

    # --- Azure OpenAI ---
    AZURE_API_KEY: str = ""
    AZURE_ENDPOINT: str = ""
    AZURE_API_VERSION: str = "2024-02-15-preview"
    AZURE_DEPLOYMENT: str = ""
    AZURE_MAX_TOKENS: int = 4096
    AZURE_TEMPERATURE: float = 0.1

    # --- Google Gemini ---
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-1.5-pro"
    GEMINI_MAX_TOKENS: int = 4096
    GEMINI_TEMPERATURE: float = 0.1

    # --- Ollama (Local) ---
    OLLAMA_BASE_URL: str = "http://localhost:11434/v1"
    OLLAMA_MODEL: str = "llama3.1:70b"
    OLLAMA_MAX_TOKENS: int = 4096
    OLLAMA_TEMPERATURE: float = 0.1

    # --- Team Key (Competition) ---
    TEAM_KEY_API_URL: str = ""
    TEAM_KEY_API_KEY: str = ""
    TEAM_KEY_MODEL: str = ""
    TEAM_KEY_SPENDING_CAP: float = 100.0

    # =========================================================================
    # Strategy Configuration
    # =========================================================================
    STRATEGY_NAME: Literal["smc", "mean_reversion", "momentum", "combined"] = "smc"

    SMC_LOOKBACK_BARS: int = 500
    SMC_SWING_LENGTH: int = 10
    SMC_OB_LOOKBACK: int = 50
    SMC_FVG_MIN_SIZE: float = 0.0001
    SMC_LIQUIDITY_LOOKBACK: int = 20

    MR_BB_PERIOD: int = 20
    MR_BB_STD: float = 2.0
    MR_RSI_PERIOD: int = 14
    MR_RSI_OVERBOUGHT: float = 70.0
    MR_RSI_OVERSOLD: float = 30.0

    MOM_MACD_FAST: int = 12
    MOM_MACD_SLOW: int = 26
    MOM_MACD_SIGNAL: int = 9
    MOM_ADX_PERIOD: int = 14
    MOM_ADX_THRESHOLD: float = 25.0

    REVIEW_INTERVAL_MINUTES: int = 60
    REVIEW_ENABLED: bool = True

    # =========================================================================
    # Risk Management
    # =========================================================================
    MAX_POSITION_SIZE: float = 0.1
    MAX_DRAWDOWN: float = 0.05
    MAX_SECTOR_EXPOSURE: float = 0.3
    MAX_CORRELATED_EXPOSURE: float = 0.2
    STOP_LOSS_PCT: float = 0.02
    TAKE_PROFIT_PCT: float = 0.04
    RISK_PER_TRADE: float = 0.01
    KELLY_FRACTION: float = 0.25
    MIN_LIQUIDITY_VOLUME: int = 100000

    # =========================================================================
    # Dashboard
    # =========================================================================
    DASHBOARD_ENABLED: bool = True
    DASHBOARD_HOST: str = "0.0.0.0"
    DASHBOARD_PORT: int = 8080
    DASHBOARD_UPDATE_INTERVAL: int = 5

    # =========================================================================
    # Compliance & Logging
    # =========================================================================
    LOG_DIR: Path = Path("./logs")
    REPORT_DIR: Path = Path("./reports")
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    LOG_ROTATION: str = "1 day"
    LOG_RETENTION: str = "30 days"
    OPERATION_LOG_ENABLED: bool = True
    CHANGE_TRACKING_ENABLED: bool = True

    # =========================================================================
    # Trading Universe
    # =========================================================================
    DEFAULT_SYMBOLS: list[str] = Field(
        default_factory=lambda: [
            "SPY", "QQQ", "IWM", "DIA",
            "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA",
            "JPM", "BAC", "GS", "MS",
            "XOM", "CVX",
            "JNJ", "PFE", "UNH",
        ]
    )
    MAX_SYMBOLS: int = 20

    # =========================================================================
    # Execution
    # =========================================================================
    ORDER_TYPE: Literal["MKT", "LMT", "STP_LMT"] = "LMT"
    ORDER_TIF: Literal["DAY", "GTC", "IOC", "FOK"] = "DAY"
    SLIPPAGE_TOLERANCE: float = 0.001

    # =========================================================================
    # Health & Monitoring
    # =========================================================================
    HEALTH_CHECK_INTERVAL: int = 30
    METRICS_ENABLED: bool = True
    ALERT_WEBHOOK_URL: str = ""

    @field_validator("LOG_DIR", "REPORT_DIR", mode="before")
    @classmethod
    def ensure_path(cls, v: str | Path) -> Path:
        return Path(v) if isinstance(v, str) else v

    @field_validator("DEFAULT_SYMBOLS", mode="before")
    @classmethod
    def parse_symbols(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [s.strip().upper() for s in v.split(",")]
        return [s.upper() for s in v]

    def get_llm_config(self) -> dict:
        """Get LLM configuration based on provider."""
        provider = self.LLM_PROVIDER

        if provider == "openrouter":
            return {
                "provider": "openrouter",
                "api_key": self.OPENROUTER_API_KEY,
                "base_url": self.OPENROUTER_BASE_URL,
                "model": self.OPENROUTER_MODEL,
                "max_tokens": self.OPENROUTER_MAX_TOKENS,
                "temperature": self.OPENROUTER_TEMPERATURE,
            }
        elif provider == "anthropic":
            return {
                "provider": "anthropic",
                "api_key": self.ANTHROPIC_API_KEY,
                "model": self.ANTHROPIC_MODEL,
                "max_tokens": self.ANTHROPIC_MAX_TOKENS,
                "temperature": self.ANTHROPIC_TEMPERATURE,
            }
        elif provider == "openai":
            return {
                "provider": "openai",
                "api_key": self.OPENAI_API_KEY,
                "base_url": self.OPENAI_BASE_URL,
                "model": self.OPENAI_MODEL,
                "max_tokens": self.OPENAI_MAX_TOKENS,
                "temperature": self.OPENAI_TEMPERATURE,
            }
        elif provider == "azure":
            return {
                "provider": "azure",
                "api_key": self.AZURE_API_KEY,
                "endpoint": self.AZURE_ENDPOINT,
                "api_version": self.AZURE_API_VERSION,
                "deployment": self.AZURE_DEPLOYMENT,
                "max_tokens": self.AZURE_MAX_TOKENS,
                "temperature": self.AZURE_TEMPERATURE,
            }
        elif provider == "gemini":
            return {
                "provider": "gemini",
                "api_key": self.GEMINI_API_KEY,
                "model": self.GEMINI_MODEL,
                "max_tokens": self.GEMINI_MAX_TOKENS,
                "temperature": self.GEMINI_TEMPERATURE,
            }
        elif provider == "ollama":
            return {
                "provider": "ollama",
                "base_url": self.OLLAMA_BASE_URL,
                "model": self.OLLAMA_MODEL,
                "max_tokens": self.OLLAMA_MAX_TOKENS,
                "temperature": self.OLLAMA_TEMPERATURE,
            }
        elif provider == "team_key":
            return {
                "provider": "team_key",
                "api_key": self.TEAM_KEY_API_KEY,
                "base_url": self.TEAM_KEY_API_URL,
                "model": self.TEAM_KEY_MODEL,
                "max_tokens": self.OPENROUTER_MAX_TOKENS,
                "temperature": self.OPENROUTER_TEMPERATURE,
            }
        else:  # mock
            return {
                "provider": "mock",
                "model": "mock",
            }

    def is_competition_mode(self) -> bool:
        return self.MODE in ("trial", "live")

    def is_live_trading(self) -> bool:
        return self.MODE == "live"


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    return settings