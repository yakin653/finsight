"""
FinSight — Backtesting d'une stratégie de croisement de moyennes mobiles.

Compare la stratégie à un simple Buy & Hold, en tenant compte
des frais de transaction et en calculant les métriques de risque.

Usage :
    python ml/src/backtest.py --symbol AAPL
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine
from dotenv import load_dotenv
import os

# Importer risk.py
sys.path.insert(0, str(Path(__file__).resolve().parent))
import risk   # noqa: E402

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

CAPITAL_INITIAL = 10_000
COST_PER_TRADE = 0.001   # 0,1 % à chaque changement de signal


def load_prices(symbol: str) -> pd.DataFrame:
    """Charge les prix d'un symbole depuis PostgreSQL."""
    engine = create_engine(DATABASE_URL)
    df = pd.read_sql(
        f"SELECT * FROM market_data WHERE symbol = '{symbol}' ORDER BY \"Date\"",
        engine,
        parse_dates=["Date"],
    )
    if df.empty:
        raise SystemExit(f"❌ Aucune donnée pour {symbol}")
    return df


def ma_crossover_signal(df: pd.DataFrame, fast: int = 20, slow: int = 50) -> pd.Series:
    """
    Signal 0/1 : 1 si MA_fast > MA_slow (on est long), 0 sinon.
    ⚠️ shift(1) : on agit le lendemain, pas le jour même (pas de fuite !)
    """
    ma_fast = df["Close"].rolling(fast).mean()
    ma_slow = df["Close"].rolling(slow).mean()
    signal = (ma_fast > ma_slow).astype(int)
    return signal.shift(1).fillna(0).astype(int)


def apply_transaction_costs(signal: pd.Series, cost: float = COST_PER_TRADE) -> pd.Series:
    """Renvoie le coût à soustraire chaque jour (0 si pas de changement)."""
    changes = signal.diff().abs().fillna(0)   # 1 si on change de position
    return changes * cost


def run_backtest(df: pd.DataFrame, signal: pd.Series, capital: float = CAPITAL_INITIAL) -> pd.DataFrame:
    """
    Simule la stratégie et renvoie un df avec :
    - return        : rendement journalier du sous-jacent
    - signal        : 0/1
    - strat_ret     : rendement de la stratégie (après frais)
    - equity        : capital cumulé de la stratégie
    - buyhold       : capital cumulé en Buy & Hold
    """
    out = df.copy()
    out["return"] = out["Close"].pct_change().fillna(0)

    # Rendement de la stratégie AVANT frais
    raw_strat = signal * out["return"]

    # Frais
    costs = apply_transaction_costs(signal)
    out["strat_ret"] = raw_strat - costs

    # Equity
    out["equity"]  = capital * (1 + out["strat_ret"]).cumprod()
    out["buyhold"] = capital * (1 + out["return"]).cumprod()

    # Signal pour info
    out["signal"] = signal

    return out


def print_report(bt: pd.DataFrame) -> None:
    """Affiche un rapport clair : stratégie vs buy & hold."""
    strat_metrics = risk.summary(bt["strat_ret"], bt["equity"])
    bh_metrics    = risk.summary(bt["return"],    bt["buyhold"])

    print("\n" + "=" * 60)
    print(f"{'Métrique':<18} {'Stratégie':>15} {'Buy & Hold':>15}")
    print("-" * 60)
    for key in ["total_return", "cagr", "volatility", "sharpe", "sortino", "max_drawdown"]:
        s = strat_metrics[key]
        b = bh_metrics[key]
        print(f"{key:<18} {s:>14.2%}  {b:>14.2%}" if "return" in key or key in ("volatility", "max_drawdown")
              else f"{key:<18} {s:>15.3f} {b:>15.3f}")
    print("=" * 60)

    final_strat = bt["equity"].iloc[-1]
    final_bh    = bt["buyhold"].iloc[-1]
    print(f"Capital final — Stratégie : {final_strat:>10,.2f} €")
    print(f"Capital final — Buy&Hold  : {final_bh:>10,.2f} €")
    print(f"Nb de trades (changements) : {int(bt['signal'].diff().abs().sum())}")
    print("=" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="AAPL")
    parser.add_argument("--fast",   type=int, default=20)
    parser.add_argument("--slow",   type=int, default=50)
    args = parser.parse_args()

    print(f"📈 Backtest {args.symbol} (MA{args.fast}/MA{args.slow})")

    df = load_prices(args.symbol)
    signal = ma_crossover_signal(df, fast=args.fast, slow=args.slow)
    bt = run_backtest(df, signal)

    print_report(bt)

    # Petit graphique ASCII de la fin
    last = bt.tail(3)[["Date", "Close", "signal", "equity", "buyhold"]]
    print(last.to_string(index=False))


if __name__ == "__main__":
    main()