from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
import os

# psycopg 3 exige le schéma postgresql+psycopg. « db » est le service Docker.
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:monmdp@db:5432/finsight")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
