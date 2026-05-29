"""SQLAlchemy models for KarmaForge SaaS."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text,
    ForeignKey, JSON, create_engine, Index,
)
from sqlalchemy.orm import DeclarativeBase, relationship, Session


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


class User(Base):
    __tablename__ = "users"

    id = Column(String(32), primary_key=True, default=_new_id)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=True)
    oauth_provider = Column(String(32), nullable=True)
    oauth_id = Column(String(255), nullable=True)
    display_name = Column(String(128), nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    generations = relationship("Generation", back_populates="user", order_by="Generation.created_at.desc()")
    feedback = relationship("Feedback", back_populates="user", order_by="Feedback.tracked_at.desc()")


class Generation(Base):
    __tablename__ = "generations"

    id = Column(String(32), primary_key=True, default=_new_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    generation_id = Column(String(32), unique=True, nullable=False)
    user_input = Column(Text, nullable=False)
    target_subreddit = Column(String(64), nullable=True)
    titles_json = Column(JSON, default=list)
    selected_title = Column(String(512), nullable=True)
    body = Column(Text, nullable=True)
    pattern_id = Column(String(64), nullable=True)
    metadata_json = Column(JSON, default=dict)
    self_check_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=_utcnow)

    user = relationship("User", back_populates="generations")
    feedback = relationship("Feedback", back_populates="generation", uselist=False)


class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(String(32), primary_key=True, default=_new_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    generation_id = Column(String(32), ForeignKey("generations.generation_id"), nullable=True)
    url = Column(String(512), default="")
    subreddit = Column(String(64), nullable=False)
    title = Column(Text, nullable=False)
    body = Column(Text, default="")
    pattern_id = Column(String(64), nullable=True)
    actual_upvotes = Column(Integer, default=0)
    num_comments = Column(Integer, default=0)
    upvote_ratio = Column(Float, default=0.0)
    performance = Column(String(16), default="unknown")
    subreddit_median = Column(Float, default=0.0)
    tracked_at = Column(DateTime, default=_utcnow)

    user = relationship("User", back_populates="feedback")
    generation = relationship("Generation", back_populates="feedback")


class SubredditConfig(Base):
    __tablename__ = "subreddit_configs"

    id = Column(String(32), primary_key=True, default=_new_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    subreddit = Column(String(64), nullable=False)
    is_active = Column(Boolean, default=True)
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=_utcnow)


def create_engine_from_url(db_url: str):
    return create_engine(db_url, pool_size=10, max_overflow=20)


def init_db(engine) -> None:
    Base.metadata.create_all(engine)


def get_session(engine) -> Session:
    return Session(engine)
