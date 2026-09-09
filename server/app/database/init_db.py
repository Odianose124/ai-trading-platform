from app.database.connection import Base, engine
from app.models.user import User


def initialize_database():
    Base.metadata.create_all(bind=engine)