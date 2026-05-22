"""Unified data schemas for KarmaForge v1.

All modules communicate through these dataclass types. No raw dicts across module boundaries.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Optional


class ContentType(Enum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    LINK = "link"
    POLL = "poll"

    @classmethod
    def from_string(cls, s: str) -> "ContentType":
        mapping = {
            "text": cls.TEXT, "self": cls.TEXT,
            "image": cls.IMAGE, "img": cls.IMAGE, "photo": cls.IMAGE,
            "video": cls.VIDEO, "gif": cls.VIDEO,
            "link": cls.LINK, "url": cls.LINK,
            "poll": cls.POLL,
        }
        return mapping.get(s.lower().strip(), cls.TEXT)


class Tier(Enum):
    T1 = "t1"  # 20M+ subscribers
    T2 = "t2"  # 1M-20M
    T3 = "t3"  # 100K-1M

    @classmethod
    def from_subscriber_count(cls, count: int) -> "Tier":
        if count >= 20_000_000:
            return cls.T1
        if count >= 1_000_000:
            return cls.T2
        return cls.T3


@dataclass
class Post:
    post_id: str
    subreddit: str
    title: str
    body: str = ""
    author: str = "[deleted]"
    created_utc: Optional[datetime] = None
    upvotes: int = 0
    upvote_ratio: float = 0.0
    num_comments: int = 0
    awards: dict = field(default_factory=dict)
    flair: Optional[str] = None
    is_oc: bool = False
    is_nsfw: bool = False
    content_type: ContentType = ContentType.TEXT
    is_crosspost: bool = False
    crosspost_source: Optional[str] = None
    url: Optional[str] = None
    source_dataset: str = "unknown"
    tier: Optional[Tier] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["content_type"] = self.content_type.value
        d["tier"] = self.tier.value if self.tier else None
        d["created_utc"] = self.created_utc.isoformat() if self.created_utc else None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Post":
        d = dict(d)
        d["content_type"] = ContentType.from_string(d.get("content_type", "text"))
        tier_val = d.get("tier")
        d["tier"] = Tier(tier_val) if tier_val else None
        created = d.get("created_utc")
        if created and isinstance(created, str):
            d["created_utc"] = datetime.fromisoformat(created)
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class Comment:
    comment_id: str
    post_id: str
    parent_id: str
    body: str
    author: str = "[deleted]"
    created_utc: Optional[datetime] = None
    upvotes: int = 0
    depth: int = 0
    thread_root_id: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["created_utc"] = self.created_utc.isoformat() if self.created_utc else None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Post":
        d = dict(d)
        created = d.get("created_utc")
        if created and isinstance(created, str):
            d["created_utc"] = datetime.fromisoformat(created)
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class SubredditMeta:
    name: str
    description: str = ""
    subscriber_count: int = 0
    tier: Optional[Tier] = None
    daily_activity: int = 0
    content_type_tags: list = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["tier"] = self.tier.value if self.tier else None
        return d
