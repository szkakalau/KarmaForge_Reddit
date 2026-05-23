"""Download Reddit submissions from PullPush API with score filtering.

PullPush supports score=>100 filtering — ideal for collecting viral posts.
Covers 2018-2025 for all 28 text-focused subreddits.
API docs: https://pullpush.io/
"""

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from karmaforge.storage import Database, Post
from karmaforge.storage.schemas import Tier, ContentType

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

API_BASE = "https://api.pullpush.io/reddit/search/submission/"
OUTPUT_DB = Path("data/processed/karmaforge.db")
TARGET_PER_SUB = 500
MAX_REQUESTS_PER_SUB = 15

# Tier-appropriate score thresholds
SCORE_THRESHOLDS = {
    "t1": 100,
    "t2": 50,
    "t3": 20,
}

# All 28 text-focused subreddits from config.yaml
TIER_MAP = {
    "AskReddit": Tier.T1,
    "Showerthoughts": Tier.T1,
    "todayilearned": Tier.T1,
    "worldnews": Tier.T1,
    "productivity": Tier.T2,
    "Fitness": Tier.T2,
    "personalfinance": Tier.T2,
    "science": Tier.T2,
    "books": Tier.T2,
    "cooking": Tier.T2,
    "lifehacks": Tier.T2,
    "getdisciplined": Tier.T2,
    "Entrepreneur": Tier.T2,
    "GetMotivated": Tier.T2,
    "LifeProTips": Tier.T2,
    "history": Tier.T2,
    "travel": Tier.T2,
    "programming": Tier.T2,
    "philosophy": Tier.T2,
    "AskHistorians": Tier.T2,
    "SaaS": Tier.T3,
    "kubernetes": Tier.T3,
    "digitalnomad": Tier.T3,
    "selfhosted": Tier.T3,
    "indiehackers": Tier.T3,
    "startups": Tier.T3,
    "SideProject": Tier.T3,
    "solopreneur": Tier.T3,
}

TARGET_SUBS = list(TIER_MAP.keys())


def fetch_posts(subreddit: str, min_score: int, max_requests: int = 15) -> list[dict]:
    """Fetch top viral posts from PullPush API using score-sorted + timestamp pagination."""
    all_posts = []
    before = None  # timestamp-based pagination (exclusive upper bound)

    for req_num in range(max_requests):
        params = {
            "subreddit": subreddit,
            "score": f">{min_score}",
            "sort": "desc",
            "sort_type": "score",
            "limit": 100,
        }
        if before:
            params["before"] = before

        # Build URL manually — urlencode escapes => which PullPush rejects
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{API_BASE}?{qs}"
        logger.debug("  [%d] %s", req_num + 1, url)

        req = Request(url, headers={"User-Agent": "karmaforge-v1-research/0.1"})
        try:
            with urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
        except HTTPError as e:
            logger.warning("  HTTP %d for r/%s: %s", e.code, subreddit, e.reason)
            if e.code == 429:
                retry_after = int(e.headers.get("Retry-After", "30"))
                logger.info("  Rate limited, waiting %ds...", retry_after)
                time.sleep(retry_after)
                continue
            break
        except Exception as e:
            logger.warning("  Request failed for r/%s: %s", subreddit, e)
            break

        posts = data.get("data", data) if isinstance(data, dict) else data
        if not posts or not isinstance(posts, list):
            logger.debug("  No more data")
            break

        all_posts.extend(posts)
        if len(posts) < 100:
            break

        # Paginate: exclude posts we've seen by setting before to the oldest timestamp
        timestamps = []
        for p in posts:
            ts = p.get("created_utc", 0)
            timestamps.append(int(float(ts)) if ts else 0)
        oldest_ts = min(timestamps) if timestamps else 0
        if oldest_ts == 0 or oldest_ts == before:
            break
        before = oldest_ts - 1

        time.sleep(0.6)

    return all_posts


def convert_to_post(raw: dict, subreddit: str) -> Post | None:
    """Convert PullPush API response to Post dataclass."""
    created_utc_val = raw.get("created_utc")
    if created_utc_val:
        try:
            created = datetime.fromtimestamp(float(created_utc_val), tz=timezone.utc)
        except (ValueError, TypeError):
            created = None
    else:
        created = None

    post_id = raw.get("id", "")
    if not post_id:
        return None
    if not post_id.startswith("t3_"):
        post_id = f"t3_{post_id}"

    is_self = raw.get("is_self", True)
    url = raw.get("url", "")
    post_hint = raw.get("post_hint", "")
    over_18 = raw.get("over_18", False)

    content_type = ContentType.TEXT
    if post_hint == "image" or any(
        x in (url or "").lower() for x in [".jpg", ".png", ".gif", "imgur.com", "i.redd.it"]
    ):
        content_type = ContentType.IMAGE
    elif post_hint == "hosted:video" or "v.redd.it" in url:
        content_type = ContentType.VIDEO
    elif url and not is_self:
        content_type = ContentType.LINK

    tier = TIER_MAP.get(subreddit, Tier.T2)

    return Post(
        post_id=post_id,
        subreddit=subreddit,
        title=raw.get("title") or "",
        body=raw.get("selftext") or "",
        author=raw.get("author") or "[deleted]",
        created_utc=created,
        upvotes=int(raw.get("score", 0)),
        upvote_ratio=float(raw.get("upvote_ratio", 0) or 0),
        num_comments=int(raw.get("num_comments", 0)),
        flair=raw.get("link_flair_text"),
        is_oc=False,
        is_nsfw=bool(over_18),
        content_type=content_type,
        url=url if url else None,
        source_dataset="pullpush",
        tier=tier,
    )


def main():
    logger.info("PullPush download for 28 text-focused subreddits")
    logger.info("Target: %d posts/sub, score thresholds vary by tier", TARGET_PER_SUB)

    db = Database(OUTPUT_DB)
    db.create_schema()

    # Get existing counts
    existing_by_sub = {}
    for row in db.conn.execute("SELECT subreddit, COUNT(*) FROM posts GROUP BY subreddit"):
        existing_by_sub[row[0]] = row[1]
    logger.info("DB has %d subreddits with existing data", len(existing_by_sub))

    total_added = 0
    per_sub_stats = {}

    for subreddit in TARGET_SUBS:
        tier = TIER_MAP.get(subreddit, Tier.T2)
        min_score = SCORE_THRESHOLDS.get(tier.value, 50)

        existing = existing_by_sub.get(subreddit, 0)
        needed = max(0, TARGET_PER_SUB - existing)

        if needed == 0:
            logger.info("r/%-22s: already at %d posts, skipping", subreddit, existing)
            per_sub_stats[subreddit] = {"existing": existing, "added": 0}
            continue

        logger.info("r/%-22s: has %d, need %d more (min_score=%d)", subreddit, existing, needed, min_score)
        raw_posts = fetch_posts(subreddit, min_score, MAX_REQUESTS_PER_SUB)
        logger.info("  Got %d raw posts from PullPush", len(raw_posts))

        if not raw_posts:
            logger.warning("  r/%s: no posts found", subreddit)
            per_sub_stats[subreddit] = {"existing": existing, "added": 0}
            continue

        # Get existing post_ids for dedup
        seen_ids = set()
        for row in db.conn.execute("SELECT post_id FROM posts WHERE subreddit=?", (subreddit,)):
            seen_ids.add(row[0])

        posts = []
        for raw in raw_posts:
            try:
                post = convert_to_post(raw, subreddit)
                if post is None:
                    continue
                if post.post_id not in seen_ids and post.title and post.upvotes >= 1:
                    posts.append(post)
                    seen_ids.add(post.post_id)
                    if len(posts) >= needed:
                        break
            except Exception as e:
                logger.debug("  Skipping post: %s", e)
                continue

        if posts:
            db.insert_posts(posts)
            logger.info(
                "  r/%s: inserted %d new posts (score %d-%d, dates %s → %s)",
                subreddit, len(posts),
                min(p.upvotes for p in posts),
                max(p.upvotes for p in posts),
                min((p.created_utc.strftime("%Y-%m-%d") if p.created_utc else "?") for p in posts),
                max((p.created_utc.strftime("%Y-%m-%d") if p.created_utc else "?") for p in posts),
            )
            total_added += len(posts)
            per_sub_stats[subreddit] = {"existing": existing, "added": len(posts)}
        else:
            logger.warning("  r/%s: 0 new valid posts after filtering", subreddit)
            per_sub_stats[subreddit] = {"existing": existing, "added": 0}

    logger.info("=" * 60)
    logger.info("Download complete! Added %d new posts from PullPush", total_added)

    # Summary by tier
    for tier in ["t1", "t2", "t3"]:
        row = db.conn.execute(
            "SELECT COUNT(*), COUNT(DISTINCT subreddit), MIN(upvotes), MAX(upvotes), AVG(upvotes) "
            "FROM posts WHERE tier=?",
            (tier,),
        ).fetchone()
        logger.info(
            "  %s: %d posts across %d subreddits, score %d-%d, avg %.0f",
            tier, row[0], row[1], row[2], row[3], row[4],
        )

    # Year distribution
    logger.info("Year distribution:")
    years = db.conn.execute(
        "SELECT SUBSTR(created_utc, 1, 4) as yr, COUNT(*) FROM posts "
        "GROUP BY yr ORDER BY yr"
    ).fetchall()
    for yr, cnt in years:
        bar = "█" * min(cnt // 200, 40)
        logger.info("  %s: %5d %s", yr, cnt, bar)

    db.conn.close()

    # Print per-subreddit summary for report
    print("\n--- Per-Subreddit Summary ---")
    for sub, stats in per_sub_stats.items():
        total = stats["existing"] + stats["added"]
        flag = "NEW" if stats["existing"] == 0 else ""
        print(f"  {sub:25s}: {stats['existing']:4d} existing + {stats['added']:4d} new = {total:5d} total  {flag}")


if __name__ == "__main__":
    main()
