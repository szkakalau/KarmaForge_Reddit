"""Performance classification and subreddit benchmark queries."""

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


def classify_performance(upvotes: int, subreddit_median: float) -> str:
    """Classify post performance relative to subreddit median.

    Returns one of: "super_viral", "viral", "passing", "failed"
    """
    if subreddit_median <= 0:
        return "passing" if upvotes > 0 else "failed"

    ratio = upvotes / subreddit_median
    if ratio >= 10:
        return "super_viral"
    elif ratio >= 3:
        return "viral"
    elif ratio >= 1.5:
        return "passing"
    return "failed"


def get_subreddit_median(db_path: str | Path, subreddit: str) -> float:
    """Get median upvotes for a subreddit from the v1 database."""
    try:
        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY upvotes) "
            "FROM posts WHERE subreddit=?",
            (subreddit,),
        ).fetchone()
        conn.close()
        if row and row[0] is not None:
            return float(row[0])
        return 50.0
    except Exception as e:
        logger.warning("Failed to get median for r/%s: %s", subreddit, e)
        return 50.0


def get_performance_label(upvotes: int, subreddit_median: float) -> str:
    """Human-readable performance label."""
    perf = classify_performance(upvotes, subreddit_median)
    labels = {
        "super_viral": f"super viral ({upvotes} votes, {subreddit_median:.0f} median)",
        "viral": f"viral ({upvotes} votes, {subreddit_median:.0f} median)",
        "passing": f"passing ({upvotes} votes, {subreddit_median:.0f} median)",
        "failed": f"failed ({upvotes} votes, {subreddit_median:.0f} median)",
    }
    return labels.get(perf, str(perf))
