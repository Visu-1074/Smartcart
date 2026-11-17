import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy import inspect, text

DEFAULT_DATABASE_URL = "sqlite:////tmp/smartcart.db" if os.getenv("VERCEL") == "1" else "sqlite:///./smartcart.db"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def migrate_dev_schema() -> None:
    """Small additive SQLite migration for the local demo database."""
    if not DATABASE_URL.startswith("sqlite"):
        return
    columns = {column["name"] for column in inspect(engine).get_columns("cart_items")}
    with engine.begin() as connection:
        for name, sql_type in (("category", "VARCHAR DEFAULT 'general'"), ("variant", "VARCHAR DEFAULT ''"), ("is_rx", "BOOLEAN DEFAULT 0")):
            if name not in columns:
                connection.execute(text(f"ALTER TABLE cart_items ADD COLUMN {name} {sql_type}"))
