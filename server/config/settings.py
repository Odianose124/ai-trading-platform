from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


SERVER_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    APP_NAME: str = "AI Trading Platform API"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"

    JWT_SECRET_KEY: str = "change-this-secret-key"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    BINANCE_SPOT_WS_URL: str = "wss://stream.binance.com:9443/ws"
    MARKET_DATA_RECONNECT_DELAY_SECONDS: int = 5

    MT5_INSTALL_ROOT: str = r"C:\Program Files\MetaTrader 5"
    MT5_RUNTIME_ROOT: str | None = None
    MT5_SERVER_DATA_ROOT: str | None = None
    MT5_TERMINAL_EXECUTABLE: str = "terminal64.exe"

    model_config = SettingsConfigDict(
        env_file=SERVER_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
