"""
FinSight - Interface Streamlit.

Dashboard financier avec :
- Signal ACHAT/VENTE/NEUTRE en haut
- 3 onglets : Analyse / News / Marche

Lancement :
    streamlit run frontend/app.py
"""
import os
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(
    page_title="FinSight",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .verdict-card {
        background: linear-gradient(135deg, #131826 0%, #1a2033 100%);
        padding: 1.5rem;
        border-radius: 16px;
        border: 1px solid #232a3d;
        margin-bottom: 1rem;
    }
    .verdict-buy    { border-left: 6px solid #10b981; }
    .verdict-sell   { border-left: 6px solid #ef4444; }
    .verdict-hold   { border-left: 6px solid #eab308; }
    .verdict-signal { font-size: 32px; font-weight: 700; margin: 0; }
    .verdict-label  { font-size: 13px; color: #9ca3af; margin: 0; text-transform: uppercase; letter-spacing: 1px; }
    .verdict-conf   { font-size: 24px; font-weight: 600; margin-top: 4px; }
    .factor-row {
        display: flex; justify-content: space-between;
        padding: 6px 0; border-bottom: 1px solid #232a3d;
    }
    .factor-name { color: #d1d5db; }
    .factor-score-pos { color: #10b981; font-weight: 600; }
    .factor-score-neg { color: #ef4444; font-weight: 600; }
    .factor-score-neu { color: #eab308; font-weight: 600; }
    .news-positive { border-left: 4px solid #10b981; padding-left: 12px; }
    .news-negative { border-left: 4px solid #ef4444; padding-left: 12px; }
    .news-neutral  { border-left: 4px solid #eab308; padding-left: 12px; }
    .news-headline { font-size: 15px; font-weight: 500; margin: 0; }
    .news-meta     { font-size: 12px; color: #9ca3af; margin-top: 2px; }
    .badge { display: inline-block; padding: 2px 8px; border-radius: 6px; font-size: 11px; font-weight: 600; }
    .badge-pos { background: #10b981; color: white; }
    .badge-neg { background: #ef4444; color: white; }
    .badge-neu { background: #eab308; color: black; }
</style>
""", unsafe_allow_html=True)


# --- Header ---
col_logo, col_status = st.columns([4, 1])
with col_logo:
    st.title("📊 FinSight")
    st.caption("Analyse financiere propulsee par ML + NLP + LLM local")
with col_status:
    try:
        requests.get(f"{API_URL}/health", timeout=3)
        st.success("🟢 API en ligne")
    except Exception:
        st.error("🔴 API hors ligne")


# --- Sidebar ---
with st.sidebar:
    st.header("⚙️ Parametres")

    try:
        r = requests.get(f"{API_URL}/assets", timeout=5)
        r.raise_for_status()
        symbols = r.json()
    except Exception as e:
        st.error(f"❌ API non joignable : {e}")
        st.stop()

    default_idx = symbols.index("AAPL") if "AAPL" in symbols else 0
    symbol = st.selectbox("Actif", symbols, index=default_idx)

    st.divider()
    st.caption(f"API : `{API_URL}`")
    st.caption(f"Heure : {datetime.now().strftime('%H:%M:%S')}")


# --- Charger les donnees ---
try:
    info = requests.get(f"{API_URL}/assets/{symbol}", timeout=10).json()
except Exception as e:
    st.error(f"❌ Impossible de charger {symbol} : {e}")
    st.stop()

try:
    signal_data = requests.get(f"{API_URL}/signal/{symbol}", timeout=10).json()
except Exception:
    signal_data = None


# --- Metriques rapides ---
col1, col2, col3, col4 = st.columns(4)
col1.metric("Prix actuel", f"{info['prix_actuel']:.2f} $")
col2.metric("MA20", f"{info['ma20']:.2f} $")
col3.metric("MA50", f"{info['ma50']:.2f} $")
col4.metric("Tendance", info["tendance"])


# --- CARTE VERDICT (le signal en gros) ---
if signal_data:
    sig = signal_data["signal"]
    css_class = {
        "ACHAT": "verdict-buy",
        "VENTE": "verdict-sell",
        "NEUTRE": "verdict-hold",
    }.get(sig, "verdict-hold")

    col_card, col_gauge = st.columns([2, 1])

    with col_card:
        st.markdown(f"""
        <div class="verdict-card {css_class}">
            <p class="verdict-label">Signal global</p>
            <p class="verdict-signal">{signal_data['emoji']} {sig}</p>
            <p class="verdict-conf">Confiance : {signal_data['confidence_pct']:.0f}%</p>
            <p style="color:#9ca3af; font-size: 13px; margin-top: 8px;">
                Score composite : <b>{signal_data['score']:+.2f} / {signal_data['max_score']:.1f}</b>
            </p>
        </div>
        """, unsafe_allow_html=True)

        # Les 3 facteurs
        comps = signal_data["components"]
        for key, label in [("technique", "📈 Technique"), ("sentiment", "📰 Sentiment"), ("ml", "🤖 ML")]:
            c = comps[key]
            score = c["score"]
            css = "factor-score-pos" if score > 0 else "factor-score-neg" if score < 0 else "factor-score-neu"
            st.markdown(f"""
            <div class="factor-row">
                <span class="factor-name">{label} — {c['reason']}</span>
                <span class="{css}">{score:+.1f}</span>
            </div>
            """, unsafe_allow_html=True)

    with col_gauge:
        # Jauge circulaire de confiance
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=signal_data["confidence_pct"],
            number={"suffix": "%", "font": {"size": 36, "color": "#e5e7eb"}},
            gauge={
                "axis": {"range": [0, 100], "tickcolor": "#6b7280"},
                "bar": {"color": "#10b981" if sig == "ACHAT" else "#ef4444" if sig == "VENTE" else "#eab308"},
                "bgcolor": "#131826",
                "borderwidth": 2,
                "bordercolor": "#232a3d",
                "steps": [
                    {"range": [0, 40], "color": "#1f2937"},
                    {"range": [40, 70], "color": "#374151"},
                    {"range": [70, 100], "color": "#4b5563"},
                ],
            },
        ))
        fig_gauge.update_layout(
            height=250,
            margin=dict(l=20, r=20, t=40, b=10),
            template="plotly_dark",
            paper_bgcolor="#0a0e1a",
            font={"color": "#e5e7eb"},
        )
        st.plotly_chart(fig_gauge, use_container_width=True)

st.divider()


# --- 3 onglets ---
tab_analyse, tab_news, tab_marche = st.tabs(["📈 Analyse", "📰 News", "🌡 Marche"])


# ===========================================================================
# ONGLET 1 : Analyse (chandelier + volume)
# ===========================================================================
with tab_analyse:
    st.subheader(f"📈 {symbol} - Historique des prix")

    try:
        hist = requests.get(f"{API_URL}/assets/{symbol}/history?limit=500", timeout=15).json()
        df = pd.DataFrame(hist["points"])
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)

        df["ma20"] = df["close"].rolling(20).mean()
        df["ma50"] = df["close"].rolling(50).mean()

        # --- Graphique chandelier ---
        fig = go.Figure()

        fig.add_trace(go.Candlestick(
            x=df["date"],
            open=df["open"], high=df["high"],
            low=df["low"],  close=df["close"],
            name="Prix",
            increasing_line_color="#10b981",
            decreasing_line_color="#ef4444",
        ))

        fig.add_trace(go.Scatter(
            x=df["date"], y=df["ma20"], mode="lines",
            name="MA20", line=dict(color="#f59e0b", width=1.5),
        ))

        fig.add_trace(go.Scatter(
            x=df["date"], y=df["ma50"], mode="lines",
            name="MA50", line=dict(color="#ef4444", width=1.5),
        ))

        fig.update_layout(
            height=450,
            margin=dict(l=0, r=0, t=10, b=0),
            xaxis_title="Date", yaxis_title="Prix ($)",
            template="plotly_dark",
            paper_bgcolor="#0a0e1a",
            plot_bgcolor="#0a0e1a",
            hovermode="x unified",
            xaxis_rangeslider_visible=False,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig, use_container_width=True)

        # --- Sous-graphique Volume ---
        colors = ["#10b981" if c >= o else "#ef4444"
                  for c, o in zip(df["close"], df["open"])]

        fig_vol = go.Figure()
        fig_vol.add_trace(go.Bar(
            x=df["date"], y=df["volume"],
            marker_color=colors, name="Volume",
        ))
        fig_vol.update_layout(
            height=150,
            margin=dict(l=0, r=0, t=10, b=0),
            xaxis_title="", yaxis_title="Volume",
            template="plotly_dark",
            paper_bgcolor="#0a0e1a",
            plot_bgcolor="#0a0e1a",
            showlegend=False,
        )
        st.plotly_chart(fig_vol, use_container_width=True)

    except Exception as e:
        st.error(f"❌ Erreur graphique : {e}")

    st.divider()
    st.subheader("🤖 Analyse IA")
    st.caption("Analyse generee par un LLM local (Ollama + Qwen2.5). 30 a 60 secondes.")

    if st.button("✨ Generer l analyse", type="primary", key="btn_insight"):
        with st.spinner("Interrogation du LLM... (patience)"):
            try:
                resp = requests.get(f"{API_URL}/insight/{symbol}", timeout=180)
                resp.raise_for_status()
                data = resp.json()

                mc1, mc2, mc3 = st.columns(3)
                mc1.metric("Volatilite annuelle", f"{data['volatilite_annualisee_pct']:.2f} %")
                mc2.metric("Max drawdown", f"{data['max_drawdown_pct']:.2f} %")
                if data.get("probabilite_hausse_pct") is not None:
                    mc3.metric("Prob. hausse (ML)", f"{data['probabilite_hausse_pct']:.1f} %")
                else:
                    mc3.metric("Prob. hausse (ML)", "n/d")

                s = data["sentiment_30j"]
                st.markdown(f"**Sentiment news (30j)** : **{s['interpretation']}** (score {s['score_moyen']}, {s['nombre_articles']} articles)")

                st.info(data["analyse_llm"])
                st.caption(data["disclaimer"])
            except Exception as e:
                st.error(f"❌ Erreur : {e}")


# ===========================================================================
# ONGLET 2 : News
# ===========================================================================
with tab_news:
    st.subheader(f"📰 News & Sentiment - {symbol}")

    try:
        news_data = requests.get(f"{API_URL}/news/{symbol}?days=30&limit=50", timeout=15).json()

        if news_data["count"] == 0:
            st.info(f"Aucune news pour {symbol} sur les 30 derniers jours.")
        else:
            score = news_data["sentiment_score"]
            interpretation = news_data["interpretation"]

            c1, c2, c3 = st.columns([1, 2, 1])
            with c2:
                if interpretation == "positif":
                    st.success("### 🟢 Sentiment : POSITIF")
                elif interpretation == "negatif":
                    st.error("### 🔴 Sentiment : NEGATIF")
                else:
                    st.warning("### 🟡 Sentiment : NEUTRE")
                st.caption(f"Score agrege : **{score:+.4f}** sur {news_data['count']} articles")

            st.divider()

            df_news = pd.DataFrame(news_data["news"])
            df_news["date"] = pd.to_datetime(df_news["date"])
            df_news = df_news.sort_values("date")
            df_news["sent"] = df_news["pos"] - df_news["neg"]
            daily = df_news.groupby(df_news["date"].dt.date)["sent"].mean().reset_index()
            daily.columns = ["date", "sent"]

            fig2 = go.Figure()
            fig2.add_trace(go.Bar(
                x=daily["date"], y=daily["sent"],
                marker_color=["#10b981" if v > 0 else "#ef4444" for v in daily["sent"]],
            ))
            fig2.update_layout(
                height=250, margin=dict(l=0, r=0, t=10, b=0),
                xaxis_title="Date", yaxis_title="Score (pos - neg)",
                template="plotly_dark", paper_bgcolor="#0a0e1a",
                showlegend=False,
            )
            st.plotly_chart(fig2, use_container_width=True)

            st.divider()
            st.markdown(f"### 📰 {news_data['count']} dernieres news")

            for item in news_data["news"][:30]:
                sent = item["sentiment"]
                css_class = "news-positive" if sent == "positive" else "news-negative" if sent == "negative" else "news-neutral"
                badge_class = "badge-pos" if sent == "positive" else "badge-neg" if sent == "negative" else "badge-neu"
                badge_label = "POSITIF" if sent == "positive" else "NEGATIF" if sent == "negative" else "NEUTRE"

                date_str = pd.to_datetime(item["date"]).strftime("%d %b %Y")
                source = item.get("source") or "source inconnue"
                url = item.get("url") or "#"
                headline = item["headline"]
                pos, neu, neg = item["pos"], item["neu"], item["neg"]

                st.markdown(f"""
                <div class="{css_class}" style="margin-bottom: 14px;">
                    <p class="news-headline"><span class="badge {badge_class}">{badge_label}</span> &nbsp; {headline}</p>
                    <p class="news-meta">{date_str} · {source} · <a href="{url}" target="_blank">Lire l article</a> &nbsp;|&nbsp; pos {pos:.2f} · neu {neu:.2f} · neg {neg:.2f}</p>
                </div>
                """, unsafe_allow_html=True)

    except Exception as e:
        st.error(f"❌ Erreur news : {e}")


# ===========================================================================
# ONGLET 3 : Marche (placeholder)
# ===========================================================================
with tab_marche:
    st.subheader("🌡 Vue du marche")
    st.info("🚧 Cet onglet affichera bientot une vue d ensemble des 10 actifs.")


st.divider()
st.caption("⚠️ Projet pedagogique. Aucune information ne constitue un conseil financier.")
