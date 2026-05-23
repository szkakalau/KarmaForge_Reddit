"""Download Reddit submissions from Arctic Shift API (Pushshift successor).

Covers all text-focused subreddits for KarmaForge v1 research.
API docs: https://github.com/ArthurHeitmann/arctic_shift/tree/master/api
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

API_BASE = "https://arctic-shift.photon-reddit.com"
OUTPUT_DB = Path("data/processed/karmaforge.db")
POSTS_PER_SUBREDDIT = 1000

# Text-focused subreddits only (no image/video-heavy subs)
TIER_MAP = {
    # T1 — large general subreddits (text-focused)
    "AskReddit": Tier.T1,
    "Showerthoughts": Tier.T1,
    "todayilearned": Tier.T1,
    "worldnews": Tier.T1,
    # T2 — large/medium subreddits
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
    # T3 — niche/vertical subreddits
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


def fetch_posts(subreddit: str, limit: int = 1000) -> list[dict]:
    """Fetch posts from Arctic Shift API, paginating as needed."""
    all_posts = []
    after = None
    batch_size = 100

    while len(all_posts) < limit:
        params = {
            "subreddit": subreddit,
            "sort": "desc",
            "limit": batch_size,
        }
        if after:
            params["after"] = after

        url = f"{API_BASE}/api/posts/search?{urlencode(params)}"
        logger.debug("Fetching: %s", url)

        req = Request(url, headers={"User-Agent": "karmaforge-v1-research/0.1"})
        try:
            with urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
        except HTTPError as e:
            logger.warning("HTTP %d for r/%s: %s", e.code, subreddit, e.reason)
            break
        except Exception as e:
            logger.warning("Request failed for r/%s: %s", subreddit, e)
            break

        posts = data.get("data", data) if isinstance(data, dict) else data
        if not posts or not isinstance(posts, list):
            logger.info("r/%s: no more data (got %d total)", subreddit, len(all_posts))
            break

        all_posts.extend(posts)
        if len(posts) < batch_size:
            break

        oldest = min(p.get("created_utc", 0) for p in posts)
        if oldest == after:
            break
        after = oldest - 1

        time.sleep(0.3)

    return all_posts


def convert_to_post(raw: dict, subreddit: str) -> Post:
    """Convert Arctic Shift API response to Post dataclass."""
    created = None
    created_utc = raw.get("created_utc")
    if created_utc:
        try:
            created = datetime.fromtimestamp(float(created_utc), tz=timezone.utc)
        except (ValueError, TypeError):
            pass

    post_id = raw.get("id", "")
    if post_id and not post_id.startswith("t3_"):
        post_id = f"t3_{post_id}"

    is_self = raw.get("is_self", True)
    url = raw.get("url", "")
    post_hint = raw.get("post_hint", "")
    over_18 = raw.get("over_18", False)

    content_type = ContentType.TEXT
    if post_hint == "image" or any(x in (url or "").lower() for x in [".jpg", ".png", ".gif", "imgur.com", "i.redd.it"]):
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
        source_dataset="arctic_shift",
        tier=tier,
    )


def main():
    logger.info("Starting Arctic Shift download for %d text-focused subreddits...", len(TARGET_SUBS))

    db = Database(OUTPUT_DB)
    db.create_schema()

    existing_counts = {}
    for row in db.conn.execute("SELECT subreddit, COUNT(*) FROM posts GROUP BY subreddit"):
        existing_counts[row[0]] = row[1]
    logger.info("DB has %d subreddits with existing data", len(existing_counts))

    total_added = 0
    for subreddit in TARGET_SUBS:
        existing = existing_counts.get(subreddit, 0)
        needed = max(0, POSTS_PER_SUBREDDIT - existing)

        if needed == 0:
            logger.info("r/%s: already at target (%d posts), skipping", subreddit, existing)
            continue

        logger.info("r/%s: has %d, need %d more → downloading...", subreddit, existing, needed)
        raw_posts = fetch_posts(subreddit, POSTS_PER_SUBREDDIT)
        logger.info("  Got %d raw posts from API", len(raw_posts))

        if not raw_posts:
            logger.warning("r/%s: no posts found", subreddit)
            continue

        posts = []
        seen_ids = set()
        for row in db.conn.execute("SELECT post_id FROM posts WHERE subreddit=?", (subreddit,)):
            seen_ids.add(row[0])

        for raw in raw_posts:
            try:
                post = convert_to_post(raw, subreddit)
                if post.upvotes >= 1 and post.title and post.post_id not in seen_ids:
                    posts.append(post)
                    seen_ids.add(post.post_id)
            except Exception as e:
                logger.debug("Skipping post in r/%s: %s", subreddit, e)
                continue

        posts.sort(key=lambda p: p.upvotes, reverse=True)

        if posts:
            db.insert_posts(posts)
            logger.info("  r/%s: inserted %d new posts (score range %d - %d, dates %s - %s)",
                         subreddit, len(posts),
                         min(p.upvotes for p in posts),
                         max(p.upvotes for p in posts),
                         min(p.created_utc.strftime("%Y-%m-%d") if p.created_utc else "?" for p in posts),
                         max(p.created_utc.strftime("%Y-%m-%d") if p.created_utc else "?" for p in posts))
            total_added += len(posts)
        else:
            logger.warning("r/%s: 0 new valid posts after filtering", subreddit)

    logger.info("Done! Added %d new posts from Arctic Shift", total_added)

    for tier in ["t1", "t2", "t3"]:
        row = db.conn.execute(
            "SELECT COUNT(*), COUNT(DISTINCT subreddit) FROM posts WHERE tier=?",
            (tier,),
        ).fetchone()
        logger.info("  %s: %d posts, %d subreddits", tier, row[0], row[1])

    db.conn.close()


if __name__ == "__main__":
    main()
