"""Restore SQLite database from the existing CSV file."""
import csv
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from karmaforge.storage import Database, Post
from karmaforge.storage.schemas import Tier, ContentType

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
    "philosophy": Tier.T2,
}

CSV_PATH = Path("data/raw/kaggle/ucsd_reddit_submissions.csv")
DB_PATH = Path("data/processed/karmaforge.db")


def main():
    logger.info("Reading CSV from %s", CSV_PATH)
    posts = []

    with open(CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                created_ts = int(row.get("created_utc", "0") or "0")
                created = datetime.fromtimestamp(created_ts, tz=timezone.utc) if created_ts > 0 else None

                subreddit = row["subreddit"]

                is_self = row.get("is_self", "1") == "1"
                over_18 = row.get("over_18", "0") == "1"
                is_oc = row.get("is_original_content", "0") == "1"
                url = row.get("url", "") or None

                # Derive content type
                content_type = ContentType.TEXT
                if not is_self and url:
                    if any(x in url.lower() for x in [".jpg", ".png", ".gif", "imgur.com", "i.redd.it"]):
                        content_type = ContentType.IMAGE
                    elif url.startswith("http"):
                        content_type = ContentType.LINK

                posts.append(Post(
                    post_id=row["id"],
                    subreddit=subreddit,
                    title=row["title"],
                    body=row.get("selftext", ""),
                    author=row.get("author", "[deleted]"),
                    created_utc=created,
                    upvotes=int(row.get("score", "0") or "0"),
                    upvote_ratio=float(row.get("upvote_ratio", "0") or "0"),
                    num_comments=int(row.get("num_comments", "0") or "0"),
                    is_oc=is_oc,
                    is_nsfw=over_18,
                    content_type=content_type,
                    url=url,
                    source_dataset="huggingface_pushshift",
                    tier=TIER_MAP.get(subreddit, Tier.T2),
                ))
            except Exception as e:
                logger.warning("Skipping row: %s", e)
                continue

    logger.info("Read %d posts from CSV", len(posts))

    logger.info("Creating database at %s", DB_PATH)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = Database(DB_PATH)
    db.create_schema()
    db.insert_posts(posts)
    logger.info("Inserted %d posts into database", len(posts))

    from collections import Counter
    sub_counts = Counter(p.subreddit for p in posts)
    for sub, cnt in sub_counts.most_common():
        logger.info("  r/%s: %d posts", sub, cnt)

    db.close()
    logger.info("Done!")


if __name__ == "__main__":
    main()
