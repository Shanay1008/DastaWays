from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import ensure_sqlite_parent, get_settings

settings = get_settings()
ensure_sqlite_parent(settings.database_url)
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def initialize_database() -> None:
    Base.metadata.create_all(bind=engine)
    # create_all handles new tables, but SQLite does not add new columns to an
    # existing Phase 1 session table. These additive migrations preserve it.
    if settings.database_url.startswith("sqlite"):
        columns = {column["name"] for column in inspect(engine).get_columns("application_sessions")}
        with engine.begin() as connection:
            if "profile" not in columns:
                connection.execute(text("ALTER TABLE application_sessions ADD COLUMN profile JSON"))
            if "report" not in columns:
                connection.execute(text("ALTER TABLE application_sessions ADD COLUMN report JSON"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
