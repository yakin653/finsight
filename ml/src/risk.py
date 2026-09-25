"""
FinSight — Métriques de risque pour évaluer une stratégie.

Fonctions pures : prennent des séries, renvoient un scalaire.
"""
import numpy as np
import pandas as pd

TRADING_DAYS = 252   # nombre de jours de bourse par an


def annualized_return(returns: pd.Series) -> float:
    """Rendement annualisé (géométrique)."""
    returns = returns.dropna()
    if len(returns) == 0:
        return 0.0
    total = (1 + returns).prod()
    years = len(returns) / TRADING_DAYS
    return total ** (1 / years) - 1 if years > 0 else 0.0


def annualized_volatility(returns: pd.Series) -> float:
    """Volatilité annualisée (écart-type × √252)."""
    return returns.dropna().std() * np.sqrt(TRADING_DAYS)


def sharpe_ratio(returns: pd.Series, rf: float = 0.0) -> float:
    """
    Ratio de Sharpe : (rendement - taux sans risque) / volatilité.
    rf = taux sans risque annualisé (0.0 par défaut).
    """
    returns = returns.dropna()
    if returns.std() == 0 or len(returns) == 0:
        return 0.0
    excess = returns - rf / TRADING_DAYS
    return excess.mean() / returns.std() * np.sqrt(TRADING_DAYS)


def sortino_ratio(returns: pd.Series, rf: float = 0.0) -> float:
    """Comme Sharpe, mais ne pénalise que la volatilité baissière."""
    returns = returns.dropna()
    downside = returns[returns < 0].std()
    if downside == 0 or len(returns) == 0:
        return 0.0
    excess = returns.mean() - rf / TRADING_DAYS
    return excess / downside * np.sqrt(TRADING_DAYS)


def max_drawdown(equity: pd.Series) -> float:
    """Pire chute depuis un sommet (valeur négative, ex : -0.35 = -35 %)."""
    equity = equity.dropna()
    if len(equity) == 0:
        return 0.0
    peak = equity.cummax()
    dd = equity / peak - 1
    return dd.min()


def cagr(equity: pd.Series) -> float:
    """Taux de croissance annuel composé."""
    equity = equity.dropna()
    if len(equity) < 2:
        return 0.0
    years = len(equity) / TRADING_DAYS
    return (equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1


def summary(returns: pd.Series, equity: pd.Series) -> dict:
    """Renvoie toutes les métriques dans un dict."""
    return {
        "cagr":            round(cagr(equity), 4),
        "volatility":      round(annualized_volatility(returns), 4),
        "sharpe":          round(sharpe_ratio(returns), 4),
        "sortino":         round(sortino_ratio(returns), 4),
        "max_drawdown":    round(max_drawdown(equity), 4),
        "total_return":    round((equity.iloc[-1] / equity.iloc[0]) - 1, 4),
    }