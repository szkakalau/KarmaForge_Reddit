"""Download Reddit submissions from HuggingFaceGECLM/REDDIT_submissions.

Converts to CSV format compatible with KaggleLoader and creates SQLite database.
"""
import csv
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from datasets import load_dataset

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from karmaforge.storage import Database, Post
from karmaforge.storage.schemas import Tier

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

TIER_MAP = {
    "funny": Tier.T1, "AskReddit": Tier.T1, "pics": Tier.T1,
    "gaming": Tier.T1, "worldnews": Tier.T1, "videos": Tier.T1,
    "todayilearned": Tier.T1, "aww": Tier.T1,
    "productivity": Tier.T2, "Fitness": Tier.T2, "personalfinance": Tier.T2,
    "technology": Tier.T2, "science": Tier.T2, "books": Tier.T2,
    "cooking": Tier.T2, "lifehacks": Tier.T2, "getdisciplined": Tier.T2,
    "Entrepreneur": Tier.T2, "dataisbeautiful": Tier.T2, "InternetIsBeautiful": Tier.T2,
    "SaaS": Tier.T3, "kubernetes": Tier.T3, "digitalnomad": Tier.T3,
    "selfhosted": Tier.T3, "indiehackers": Tier.T3, "startups": Tier.T3,
    "SideProject": Tier.T3, "solopreneur": Tier.T3,
    "Games": Tier.T2, "GetMotivated": Tier.T2, "LifeProTips": Tier.T2,
    "Showerthoughts": Tier.T1, "history": Tier.T2, "space": Tier.T2,
    "sports": Tier.T2, "travel": Tier.T2, "programming": Tier.T2,
    "philosophy": Tier.T2, "AskHistorians": Tier.T2, "DIY": Tier.T2,
    "Damnthatsinteresting": Tier.T2,
}

TARGET_SPLITS = [
    # T1
    "gaming", "todayilearned", "Showerthoughts",
    # T2
    "Fitness", "books", "lifehacks", "personalfinance", "science", "technology",
    "Games", "GetMotivated", "LifeProTips", "history", "space", "sports",
    "travel", "programming", "philosophy", "AskHistorians", "DIY",
    "Damnthatsinteresting",
]

OUTPUT_CSV = Path("data/raw/kaggle/ucsd_reddit_submissions.csv")
OUTPUT_DB = Path("data/processed/karmaforge.db")
POSTS_PER_SUBREDDIT = 500


def parse_int(val) -> int:
    if val is None or str(val).strip() == "" or str(val) == "None":
        return 0
    try:
        return int(val)
    except (ValueError, TypeError):
        return 0


def parse_float(val) -> float:
    if val is None or str(val).strip() == "" or str(val) == "None":
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def parse_bool(val) -> bool:
    if val is None or str(val).strip() == "" or str(val) == "None":
        return False
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    return s in ("true", "1", "yes")


def convert_to_post(example: dict, subreddit: str) -> Post:
    score = parse_int(example.get("score", 0))
    num_comments = parse_int(example.get("num_comments", 0))
    created_utc = example.get("created_utc", "0")
    try:
        created = datetime.fromtimestamp(float(created_utc), tz=timezone.utc)
    except (ValueError, TypeError):
        created = None

    is_self = parse_bool(example.get("is_self", True))
    over_18 = parse_bool(example.get("over_18", False))
    is_oc = parse_bool(example.get("is_original_content", False))
    is_video = parse_bool(example.get("is_video", False))
    domain = str(example.get("domain", "") or "")
    url = str(example.get("url", "") or "")

    from karmaforge.storage.schemas import ContentType
    content_type = ContentType.TEXT
    if is_video:
        content_type = ContentType.VIDEO
    elif not is_self and url:
        if any(x in url.lower() for x in [".jpg", ".png", ".gif", "imgur.com", "i.redd.it"]):
            content_type = ContentType.IMAGE
        elif url.startswith("http"):
            content_type = ContentType.LINK

    name = str(example.get("name") or example.get("id") or "")
    if name and not name.startswith("t3_"):
        name = "t3_" + name

    tier = TIER_MAP.get(subreddit, Tier.T2)

    return Post(
        post_id=name,
        subreddit=subreddit,
        title=str(example.get("title") or ""),
        body=str(example.get("selftext") or ""),
        author=str(example.get("author") or "[deleted]"),
        created_utc=created,
        upvotes=score,
        upvote_ratio=parse_float(example.get("upvote_ratio", 0)),
        num_comments=num_comments,
        flair=None,
        is_oc=is_oc,
        is_nsfw=over_18,
        content_type=content_type,
        url=url if url else None,
        source_dataset="huggingface_pushshift",
        tier=tier,
    )


def main():
    logger.info("Starting Hugging Face data download...")

    all_posts: list[Post] = []

    for split in TARGET_SPLITS:
        logger.info("Downloading r/%s ...", split)
        try:
            ds = load_dataset(
                "HuggingFaceGECLM/REDDIT_submissions",
                split=split,
                streaming=True,
            )
        except Exception as e:
            logger.warning("Failed to load %s: %s", split, e)
            continue

        posts = []
        for example in ds:
            try:
                post = convert_to_post(example, split)
                if post.upvotes >= 1:
                    posts.append(post)
            except Exception:
                continue
            if len(posts) >= POSTS_PER_SUBREDDIT:
                break
        logger.info("  Collected %d posts", len(posts))

        # Sort by upvotes desc
        posts.sort(key=lambda p: p.upvotes, reverse=True)
        logger.info("  r/%s: %d posts (score range %d - %d)", split, len(posts),
                     min(p.upvotes for p in posts) if posts else 0,
                     max(p.upvotes for p in posts) if posts else 0)
        all_posts.extend(posts)

    logger.info("Total posts: %d", len(all_posts))

    # Save CSV
    logger.info("Saving CSV to %s", OUTPUT_CSV)
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "id", "subreddit", "title", "selftext", "author", "created_utc",
        "score", "upvote_ratio", "num_comments", "url", "is_self",
        "over_18", "is_original_content",
    ]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for p in all_posts:
            writer.writerow({
                "id": p.post_id,
                "subreddit": p.subreddit,
                "title": p.title,
                "selftext": p.body,
                "author": p.author,
                "created_utc": int(p.created_utc.timestamp()) if p.created_utc else 0,
                "score": p.upvotes,
                "upvote_ratio": p.upvote_ratio,
                "num_comments": p.num_comments,
                "url": p.url or "",
                "is_self": 1 if p.content_type.value == "text" else 0,
                "over_18": 1 if p.is_nsfw else 0,
                "is_original_content": 1 if p.is_oc else 0,
            })

    # Save to SQLite
    logger.info("Creating database at %s", OUTPUT_DB)
    OUTPUT_DB.parent.mkdir(parents=True, exist_ok=True)
    db = Database(OUTPUT_DB)
    db.create_schema()
    db.insert_posts(all_posts)
    logger.info("Inserted %d posts into database", len(all_posts))

    # Show stats
    from collections import Counter
    sub_counts = Counter(p.subreddit for p in all_posts)
    for sub, cnt in sub_counts.most_common():
        tier = TIER_MAP.get(sub, Tier.T2)
        logger.info("  r/%s (%s): %d posts", sub, tier.value, cnt)

    logger.info("Done!")


if __name__ == "__main__":
    main()
