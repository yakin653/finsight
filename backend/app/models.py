from sqlalchemy import Column, String, Float, Date
from .database import Base

class MarketData(Base):
    __tablename__ = "market_data"

    id = Column(String, primary_key=True, index=True)
    symbol = Column(String, index=True)
    date = Column(Date)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)