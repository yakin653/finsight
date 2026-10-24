from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import engine, Base, SessionLocal
from .models import MarketData
from .routers import assets
import datetime
import random

# Création des tables au démarrage
Base.metadata.create_all(bind=engine)

app = FastAPI(title="MarketPulse API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(assets.router)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.on_event("startup")
def seed_data():
    db = SessionLocal()
    # Si la base est vide, on insère de fausses données pour la démo
    if db.query(MarketData).count() == 0:
        symbols = ["AAPL", "MSFT", "TSLA", "NVDA", "BTC-USD"]
        today = datetime.date.today()
        for symbol in symbols:
            base_price = random.uniform(100, 500)
            for i in range(60): # 60 jours d'historique
                d = today - datetime.timedelta(days=60-i)
                price = base_price + random.uniform(-10, 10)
                db.add(MarketData(
                    id=f"{symbol}-{d}", symbol=symbol, date=d,
                    open=price-2, high=price+5, low=price-5, close=price, volume=random.randint(1000, 50000)
                ))
        db.commit()
    db.close()