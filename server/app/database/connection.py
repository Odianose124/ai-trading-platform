from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


BASE_DIR = Path(__file__).resolve().parents[2]
DATABASE_PATH = BASE_DIR / "ai_trading.db"

DATABASE_URL = f"sqlite:///{DATABASE_PATH}"


engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)


SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_database_tables():
    Base.metadata.create_all(bind=engine)


# Import models after Base has been defined so SQLAlchemy
# registers them in Base.metadata without creating a circular import.
from app.models.trade_intent import TradeIntent  # noqa: E402, F401
from app.models.user_settings import UserSettings  # noqa: E402, F401
from app.models.mt5_trading_account import MT5TradingAccount  # noqa: E402, F401
from app.models.managed_position import ManagedPosition  # noqa: E402, F401
from app.models.management_profile import ManagementProfile  # noqa: E402, F401