from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

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


class AppMeta(Base):
    """Petites clés de provenance (origine des cours, date de mise à jour)."""

    __tablename__ = "app_meta"

    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)


class User(Base):
    """Compte. Le mot de passe n'est stocké que sous forme d'empreinte."""

    __tablename__ = "users"

    id = Column(String, primary_key=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    display_name = Column(String, nullable=False)
    google_sub = Column(String, unique=True, nullable=True)
    # Augmente à chaque mot de passe : les jetons plus anciens ne sont plus acceptés.
    token_version = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class PasswordReset(Base):
    """Jeton de réinitialisation. Seule l'empreinte est stockée."""

    __tablename__ = "password_resets"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    token_hash = Column(String, nullable=False, unique=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)


class UserProfile(Base):
    """Préférences d'affichage. Ce n'est pas une évaluation d'adéquation."""

    __tablename__ = "user_profiles"

    user_id = Column(String, ForeignKey("users.id"), primary_key=True)
    level = Column(String, nullable=False, default="debutant")
    horizon = Column(String, nullable=False, default="moyen")
    risk_tolerance = Column(String, nullable=False, default="equilibre")
    goals = Column(JSONB, nullable=False, default=lambda: [])
    sectors = Column(JSONB, nullable=False, default=lambda: [])
    favorite_symbols = Column(JSONB, nullable=False, default=lambda: [])
    news_keywords = Column(JSONB, nullable=False, default=lambda: [])
    language = Column(String, nullable=False, default="fr")
    notif_prefs = Column(JSONB, nullable=False, default=lambda: {})
    onboarding_completed = Column(Boolean, nullable=False, default=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class UserSymbol(Base):
    """Symboles de la watchlist synchronisés, pour les alertes côté serveur."""

    __tablename__ = "user_symbols"

    user_id = Column(String, ForeignKey("users.id"), primary_key=True)
    symbol = Column(String, primary_key=True)


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String, nullable=False, default="Conversation")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Message(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True)
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False, index=True)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    payload = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class NewsItem(Base):
    """Titre, éditeur, lien et date. Jamais le corps de l'article."""

    __tablename__ = "news_items"

    id = Column(String, primary_key=True)
    symbol = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False)
    publisher = Column(String, nullable=False, default="")
    url = Column(String, nullable=False, unique=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    sentiment = Column(String, nullable=True)


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    news_id = Column(String, ForeignKey("news_items.id"), nullable=True)
    kind = Column(String, nullable=False, default="news")
    title = Column(String, nullable=False)
    body = Column(Text, nullable=False, default="")
    symbol = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    read_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("user_id", "news_id", "kind", name="uq_notification_news"),)


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    endpoint = Column(String, nullable=False, unique=True)
    p256dh = Column(String, nullable=False)
    auth = Column(String, nullable=False)


class AlertRule(Base):
    """Règle personnelle. Le planificateur la compare aux cours déjà stockés."""

    __tablename__ = "alert_rules"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    symbol = Column(String, nullable=False)
    kind = Column(String, nullable=False)
    threshold = Column(Float, nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    last_fired_on = Column(Date, nullable=True)
