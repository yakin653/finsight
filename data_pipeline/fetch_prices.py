"""
FinSight — Phase 1 : Récupération des prix historiques.
Télécharge via yfinance et stocke dans PostgreSQL (table market_data).
"""
import yfinance as yf
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os

load_dotenv()

# --- Config ---
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:monmdp@localhost:5432/finsight"
)
TABLE_NAME = "market_data"

# 10 actifs : actions US, crypto, or, forex, indice
SYMBOLS = [
    "AAPL",      # Apple
    "MSFT",      # Microsoft
    "TSLA",      # Tesla
    "NVDA",      # Nvidia
    "BTC-USD",   # Bitcoin
    "ETH-USD",   # Ethereum
    "GC=F",      # Or (Gold futures)
    "EURUSD=X",  # Euro / Dollar
    "^GSPC",     # S&P 500
    "^FCHI",     # CAC 40
]


def get_last_date(engine, symbol: str):
    """Retourne la date la plus récente déjà en base pour ce symbole (ou None)."""
    query = text(f"SELECT MAX(\"Date\") FROM {TABLE_NAME} WHERE symbol = :s")
    with engine.connect() as conn:
        result = conn.execute(query, {"s": symbol}).scalar()
    return result


def fetch(symbol: str, start="2018-01-01"):
    """Télécharge les prix d'un symbole."""
    df = yf.download(symbol, start=start, auto_adjust=True, progress=False)
    if df.empty:
        print(f"  ⚠️  Aucune donnée pour {symbol}")
        return None
    # yfinance récent renvoie des colonnes à 2 niveaux -> on aplatit
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.reset_index()
    df["symbol"] = symbol
    return df


def ensure_table(engine):
    """Crée la table + contrainte unique (symbol, Date) si elle n'existe pas."""
    with engine.begin() as conn:
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                "Date"   TIMESTAMP NOT NULL,
                "Open"   DOUBLE PRECISION,
                "High"   DOUBLE PRECISION,
                "Low"    DOUBLE PRECISION,
                "Close"  DOUBLE PRECISION,
                "Volume" BIGINT,
                symbol   TEXT NOT NULL,
                PRIMARY KEY (symbol, "Date")
            );
        """))


def store(df: pd.DataFrame, engine):
    """Insère les lignes en ignorant les doublons (via ON CONFLICT)."""
    if df is None or df.empty:
        return 0
    # ON CONFLICT : on ignore les lignes déjà présentes (grâce à la PK composite)
    df.to_sql(
        "market_data_tmp",
        engine,
        if_exists="replace",
        index=False,
    )
    with engine.begin() as conn:
        conn.execute(text(f"""
            INSERT INTO {TABLE_NAME} ("Date","Open","High","Low","Close","Volume",symbol)
            SELECT "Date","Open","High","Low","Close","Volume",symbol
            FROM market_data_tmp
            ON CONFLICT (symbol, "Date") DO NOTHING;
        """))
        conn.execute(text("DROP TABLE market_data_tmp;"))
    return len(df)


def main():
    engine = create_engine(DATABASE_URL)
    ensure_table(engine)

    total = 0
    for sym in SYMBOLS:
        print(f"→ {sym}")
        last = get_last_date(engine, sym)
        start = "2018-01-01" if last is None else str(last)[:10]

        df = fetch(sym, start=start)
        n = store(df, engine)
        total += n
        print(f"  ✓ {n} lignes traitées (dernière en base : {last})")

    print(f"\n✅ Terminé — {total} lignes au total.")


if __name__ == "__main__":
    main()