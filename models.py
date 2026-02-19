"""
models.py — SQLAlchemy ORM models for BeatFlow AI
Git-for-Audio schema:
  User → Repository → Commit (self-referential parent) → Stem
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Text, Float, Integer, Boolean,
    DateTime, ForeignKey, Enum, UniqueConstraint
)
from sqlalchemy.orm import relationship
from database import Base


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _uuid():
    return str(uuid.uuid4())


# ── Users ─────────────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id           = Column(String(36), primary_key=True, default=_uuid)
    username     = Column(String(50), unique=True, nullable=False, index=True)
    email        = Column(String(120), unique=True, nullable=False, index=True)
    password_hash = Column(String(128), nullable=False)
    bio              = Column(Text, default="")
    avatar_url       = Column(String(256), default="")
    library_repo_id  = Column(String(36), nullable=True)   # auto-created "My Beats" repo
    created_at       = Column(DateTime, default=_now)
    is_active        = Column(Boolean, default=True)

    repositories  = relationship("Repository", back_populates="owner", cascade="all, delete-orphan")
    starred_repos = relationship("Star",   back_populates="user",     cascade="all, delete-orphan")
    following     = relationship("Follow",  back_populates="follower", foreign_keys="[Follow.follower_id]", cascade="all, delete-orphan")
    followers     = relationship("Follow",  back_populates="followee", foreign_keys="[Follow.followee_id]", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User {self.username}>"


# ── Repositories ──────────────────────────────────────────────────
class Repository(Base):
    __tablename__ = "repositories"

    id          = Column(String(36), primary_key=True, default=_uuid)
    owner_id    = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name        = Column(String(100), nullable=False)
    description = Column(Text, default="")
    is_public   = Column(Boolean, default=True)
    forked_from = Column(String(36), ForeignKey("repositories.id"), nullable=True)
    created_at  = Column(DateTime, default=_now)
    updated_at  = Column(DateTime, default=_now, onupdate=_now)

    # Total play count (denormalized for speed)
    play_count  = Column(Integer, default=0)
    star_count  = Column(Integer, default=0)

    owner   = relationship("User", back_populates="repositories")
    commits = relationship("Commit", back_populates="repository",
                           cascade="all, delete-orphan",
                           order_by="Commit.created_at")
    fork_parent = relationship("Repository", remote_side="Repository.id", foreign_keys=[forked_from])

    def __repr__(self):
        return f"<Repository {self.name}>"


# ── Commits ───────────────────────────────────────────────────────
class Commit(Base):
    """
    Each commit = one saved version of a beat.
    parent_id → self-referential FK (like Git).
    """
    __tablename__ = "commits"

    id           = Column(String(36), primary_key=True, default=_uuid)
    repository_id = Column(String(36), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False)
    parent_id    = Column(String(36), ForeignKey("commits.id"), nullable=True)   # None = root commit
    author_id    = Column(String(36), ForeignKey("users.id"), nullable=False)

    # Content
    message      = Column(String(200), default="Beat update")
    prompt       = Column(Text, default="")           # prompt used to generate this beat
    audio_url    = Column(String(512), nullable=False) # URL of the full mix WAV
    duration     = Column(Float, default=0.0)          # seconds

    # Generation metadata
    bpm          = Column(Float, nullable=True)
    key          = Column(String(20), nullable=True)
    energy       = Column(Float, nullable=True)
    mood         = Column(String(80), nullable=True)
    model_used   = Column(String(60), default="musicgen-small")
    elapsed_sec  = Column(Float, default=0.0)         # GPU time

    # Git-style hash (short, human-readable)
    commit_hash  = Column(String(8), default=lambda: uuid.uuid4().hex[:8], unique=True)

    created_at   = Column(DateTime, default=_now)

    repository = relationship("Repository", back_populates="commits")
    author     = relationship("User")
    stems      = relationship("Stem",    back_populates="commit", cascade="all, delete-orphan")
    comments   = relationship("Comment", back_populates="commit", cascade="all, delete-orphan",
                               order_by="Comment.created_at")
    parent     = relationship("Commit", remote_side="Commit.id", foreign_keys=[parent_id])
    children   = relationship("Commit", back_populates="parent",
                               foreign_keys="[Commit.parent_id]")

    def __repr__(self):
        return f"<Commit {self.commit_hash} – {self.message[:30]}>"


# ── Stems ─────────────────────────────────────────────────────────
class Stem(Base):
    """
    Each stem is one separated audio track belonging to a Commit.
    type ∈ {drums, bass, vocals, other, full_mix}
    """
    __tablename__ = "stems"

    id         = Column(String(36), primary_key=True, default=_uuid)
    commit_id  = Column(String(36), ForeignKey("commits.id", ondelete="CASCADE"), nullable=False)
    type       = Column(
        Enum("drums", "bass", "vocals", "other", "full_mix", name="stem_type"),
        nullable=False
    )
    audio_url  = Column(String(512), nullable=False)
    file_size  = Column(Integer, default=0)   # bytes
    created_at = Column(DateTime, default=_now)

    commit = relationship("Commit", back_populates="stems")

    def __repr__(self):
        return f"<Stem {self.type} → {self.commit_id[:8]}>"


# ── Stars ─────────────────────────────────────────────────────────
class Star(Base):
    """User stars a repository (one per user-repo pair)."""
    __tablename__ = "stars"
    __table_args__ = (UniqueConstraint("user_id", "repo_id", name="uq_star"),)

    id         = Column(String(36), primary_key=True, default=_uuid)
    user_id    = Column(String(36), ForeignKey("users.id",          ondelete="CASCADE"), nullable=False)
    repo_id    = Column(String(36), ForeignKey("repositories.id",   ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=_now)

    user       = relationship("User",       back_populates="starred_repos")
    repository = relationship("Repository")

    def __repr__(self):
        return f"<Star {self.user_id[:8]} → {self.repo_id[:8]}>"


# ── Follows ───────────────────────────────────────────────────────
class Follow(Base):
    """User follows another user (one per follower-followee pair)."""
    __tablename__ = "follows"
    __table_args__ = (UniqueConstraint("follower_id", "followee_id", name="uq_follow"),)

    id           = Column(String(36), primary_key=True, default=_uuid)
    follower_id  = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    followee_id  = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at   = Column(DateTime, default=_now)

    follower = relationship("User", back_populates="following", foreign_keys=[follower_id])
    followee = relationship("User", back_populates="followers", foreign_keys=[followee_id])

    def __repr__(self):
        return f"<Follow {self.follower_id[:8]} → {self.followee_id[:8]}>"


# ── Comments ──────────────────────────────────────────────────────
class Comment(Base):
    """Text comment on a specific commit."""
    __tablename__ = "comments"

    id         = Column(String(36), primary_key=True, default=_uuid)
    commit_id  = Column(String(36), ForeignKey("commits.id",  ondelete="CASCADE"), nullable=False)
    author_id  = Column(String(36), ForeignKey("users.id",    ondelete="CASCADE"), nullable=False)
    body       = Column(Text, nullable=False)
    created_at = Column(DateTime, default=_now)

    commit = relationship("Commit", back_populates="comments")
    author = relationship("User")

    def __repr__(self):
        return f"<Comment {self.id[:8]} on {self.commit_id[:8]}>"

