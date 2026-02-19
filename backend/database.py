import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./zylmus.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

_raw_key = os.environ.get("ZYLMUS_FERNET_KEY")
if _raw_key:
    fernet = Fernet(_raw_key.encode())
else:
    # Generate a temporary key for first run; warn user
    _tmp_key = Fernet.generate_key()
    fernet = Fernet(_tmp_key)
    print(
        "WARNING: ZYLMUS_FERNET_KEY not set. "
        "A temporary key was generated — passwords will be lost on restart. "
        f"Add this to backend/.env: ZYLMUS_FERNET_KEY={_tmp_key.decode()}"
    )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
