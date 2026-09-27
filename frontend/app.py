"""
FinSight — Interface Streamlit.

Interroge l'API FastAPI (localhost:8000) et affiche :
- la liste des actifs
- les prix + tendance
- un graphique interactif
- l'analyse générée par le LLM

Lancement :
    streamlit run frontend/app.py
"""
import os
import requests
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(
    page_title="FinSight",
    page_icon="📊",
    layout="wide",
)

# --- Header ---
st.title("📊 FinSight")
st.caption("Analyse financière : prix + ML + NLP + LLM (Ollama local)")

# --- Sidebar ---
with st.sidebar:
    st.header("⚙️ Paramètres")

    try:
        r = requests.get(f"{API_URL}/assets", timeout=5)
        r.raise_for_status()
        symbols = r.json()
    except Exception as e:
        st.error(f"❌ API non joignable : {e}")
        st.stop()

    default_idx = symbols.index("AAPL") if "AAPL" in symbols else 0
    symbol = st.selectbox("Actif", symbols, index=default_idx)
    limit = st.slider("Points sur le graphique", 50, 2000, 500, step=50)

    st.divider()
    st.caption(f"API : `{API_URL}`")

# --- 1. Prix actuel + tendance ---
try:
    info = requests.get(f"{API_URL}/assets/{symbol}", timeout=10).json()
except Exception as e:
    st.error(f"❌ Impossible de charger les infos de {symbol} : {e}")
    st.stop()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Prix actuel", f"{info['prix_actuel']:.2f} $")
col2.metric("MA20", f"{info['ma20']:.2f} $")
col3.metric("MA50", f"{info['ma50']:.2f} $")
col4.metric("Tendance", info["tendance"])

# --- 2. Graphique des prix ---
st.subheader("📈 Historique des prix")

try:
    hist = requests.get(f"{API_URL}/assets/{symbol}/history?limit={limit}", timeout=15).json()
    df = pd.DataFrame(hist["points"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["close"], mode="lines",
        name="Close", line=dict(color="#3b82f6", width=2),
    ))
    fig.update_layout(
        height=400,
        margin=dict(l=0, r=0, t=10, b=0),
        xaxis_title="Date", yaxis_title="Prix ($)",
        hovermode="x unified", showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)
except Exception as e:
    st.error(f"❌ Erreur de graphique : {e}")

# --- 3. Analyse IA ---
st.subheader("🤖 Analyse IA")
st.caption("Générée par un LLM local (Ollama + Qwen2.5). Peut prendre 30 à 60 secondes.")

if st.button("✨ Générer l'analyse", type="primary"):
    with st.spinner("Interrogation du LLM en cours... (patience, ça tourne sur CPU)"):
        try:
            resp = requests.get(f"{API_URL}/insight/{symbol}", timeout=180)
            resp.raise_for_status()
            data = resp.json()

            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("Volatilité annuelle", f"{data['volatilite_annualisee_pct']:.2f} %")
            mc2.metric("Max drawdown", f"{data['max_drawdown_pct']:.2f} %")
            if data.get("probabilite_hausse_pct") is not None:
                mc3.metric("Probabilité de hausse (ML)", f"{data['probabilite_hausse_pct']:.1f} %")
            else:
                mc3.metric("Probabilité de hausse (ML)", "n/d")

            s = data["sentiment_30j"]
            st.markdown(f"**Sentiment des news (30j)** — interprétation : **{s['interpretation']}** "
                        f"(score {s['score_moyen']}, {s['nombre_articles']} articles)")

            st.info(data["analyse_llm"])
            st.caption(data["disclaimer"])

        except Exception as e:
            st.error(f"❌ Erreur : {e}")

# --- Footer ---
st.divider()
st.caption("⚠️ Ceci est un projet pédagogique. Aucune information ne constitue un conseil financier.")