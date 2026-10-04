"""
FinSight - Interface Streamlit.

Dashboard financier avec 3 onglets :
- Analyse : graphique + insight IA
- News : sentiment FinBERT visible
- Marche : vue multi-actifs (a venir)

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

# --- Config de la page ---
st.set_page_config(
    page_title="FinSight",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- CSS custom (pour peaufiner le look) ---
st.markdown("""
<style>
    .metric-card {
        background: linear-gradient(135deg, #131826 0%, #1a2033 100%);
        padding: 1rem;
        border-radius: 12px;
        border: 1px solid #232a3d;
    }
    .news-positive { border-left: 4px solid #10b981; padding-left: 12px; }
    .news-negative { border-left: 4px solid #ef4444; padding-left: 12px; }
    .news-neutral  { border-left: 4px solid #eab308; padding-left: 12px; }
    .news-headline { font-size: 15px; font-weight: 500; margin: 0; }
    .news-meta     { font-size: 12px; color: #9ca3af; margin-top: 2px; }
    .badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 6px;
        font-size: 11px;
        font-weight: 600;
    }
    .badge-pos { background: #10b981; color: white; }
    .badge-neg { background: #ef4444; color: white; }
    .badge-neu { background: #eab308; color: black; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
col_logo, col_status = st.columns([4, 1])
with col_logo:
    st.title("📊 FinSight")
    st.caption("Analyse financiere propulsee par ML + NLP + LLM local")
with col_status:
    try:
        health = requests.get(f"{API_URL}/health", timeout=3).json()
        st.success("🟢 API en ligne")
    except Exception:
        st.error("🔴 API hors ligne")


# ---------------------------------------------------------------------------
# Sidebar - Selection de l actif
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Recuperer les infos de l actif (utilise dans tous les onglets)
# ---------------------------------------------------------------------------
try:
    info = requests.get(f"{API_URL}/assets/{symbol}", timeout=10).json()
except Exception as e:
    st.error(f"❌ Impossible de charger les infos de {symbol} : {e}")
    st.stop()


# ---------------------------------------------------------------------------
# Cartes de metriques en haut (toujours visibles)
# ---------------------------------------------------------------------------
col1, col2, col3, col4 = st.columns(4)
col1.metric("Prix actuel", f"{info['prix_actuel']:.2f} $")
col2.metric("MA20", f"{info['ma20']:.2f} $")
col3.metric("MA50", f"{info['ma50']:.2f} $")
col4.metric("Tendance", info["tendance"])

st.divider()


# ---------------------------------------------------------------------------
# 3 onglets
# ---------------------------------------------------------------------------
tab_analyse, tab_news, tab_marche = st.tabs(["📈 Analyse", "📰 News", "🌡 Marche"])


# ===========================================================================
# ONGLET 1 : Analyse
# ===========================================================================
with tab_analyse:
    st.subheader(f"📈 {symbol} - Historique des prix")

    try:
        hist = requests.get(
            f"{API_URL}/assets/{symbol}/history?limit=500",
            timeout=15,
        ).json()
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
            hovermode="x unified",
            showlegend=False,
            template="plotly_dark",
        )
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"❌ Erreur de graphique : {e}")

    st.divider()
    st.subheader("🤖 Analyse IA")
    st.caption("Analyse generee par un LLM local (Ollama + Qwen2.5). 30 a 60 secondes.")

    if st.button("✨ Generer l analyse", type="primary", key="btn_insight"):
        with st.spinner("Interrogation du LLM... (patience, ca tourne sur CPU)"):
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
                st.markdown(
                    f"**Sentiment news (30j)** : **{s['interpretation']}** "
                    f"(score {s['score_moyen']}, {s['nombre_articles']} articles)"
                )

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
        news_data = requests.get(
            f"{API_URL}/news/{symbol}?days=30&limit=50",
            timeout=15,
        ).json()

        if news_data["count"] == 0:
            st.info(f"Aucune news disponible pour {symbol} sur les 30 derniers jours.")
        else:
            # --- Score de sentiment agrege ---
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

            # --- Graphique du sentiment dans le temps ---
            df_news = pd.DataFrame(news_data["news"])
            df_news["date"] = pd.to_datetime(df_news["date"])
            df_news = df_news.sort_values("date")

            # Score par jour (pos - neg)
            df_news["sent"] = df_news["pos"] - df_news["neg"]
            daily = df_news.groupby(df_news["date"].dt.date)["sent"].mean().reset_index()
            daily.columns = ["date", "sent"]

            fig2 = go.Figure()
            fig2.add_trace(go.Bar(
                x=daily["date"], y=daily["sent"],
                marker_color=["#10b981" if v > 0 else "#ef4444" for v in daily["sent"]],
                name="Sentiment",
            ))
            fig2.update_layout(
                height=250,
                margin=dict(l=0, r=0, t=10, b=0),
                xaxis_title="Date", yaxis_title="Score (pos - neg)",
                template="plotly_dark",
                showlegend=False,
            )
            st.plotly_chart(fig2, use_container_width=True)

            st.divider()

            # --- Liste des news ---
            st.markdown(f"### 📰 {news_data['count']} dernieres news")

            for item in news_data["news"][:30]:
                sent = item["sentiment"]
                if sent == "positive":
                    css_class = "news-positive"
                    badge = '<span class="badge badge-pos">POSITIF</span>'
                elif sent == "negative":
                    css_class = "news-negative"
                    badge = '<span class="badge badge-neg">NEGATIF</span>'
                else:
                    css_class = "news-neutral"
                    badge = '<span class="badge badge-neu">NEUTRE</span>'

                date_str = pd.to_datetime(item["date"]).strftime("%d %b %Y")
                source = item.get("source") or "source inconnue"
                url = item.get("url") or "#"
                headline = item["headline"]
                pos, neu, neg = item["pos"], item["neu"], item["neg"]

                st.markdown(f"""
                <div class="{css_class}" style="margin-bottom: 14px;">
                    <p class="news-headline">{badge} &nbsp; {headline}</p>
                    <p class="news-meta">
                        {date_str} · {source} ·&nbsp;
                        <a href="{url}" target="_blank">Lire l article</a>
                        &nbsp;|&nbsp; pos {pos:.2f} · neu {neu:.2f} · neg {neg:.2f}
                    </p>
                </div>
                """, unsafe_allow_html=True)

    except Exception as e:
        st.error(f"❌ Erreur lors du chargement des news : {e}")


# ===========================================================================
# ONGLET 3 : Marche (placeholder)
# ===========================================================================
with tab_marche:
    st.subheader("🌡 Vue du marche")
    st.info("🚧 Cet onglet affichera bientot une vue d ensemble des 10 actifs "
            "(performance du jour, signal, tendance). Reste branche !")


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.divider()
st.caption("⚠️ Projet pedagogique. Aucune information ne constitue un conseil financier.")
