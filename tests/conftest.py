"""Shared test fixtures for KarmaForge v1."""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from karmaforge.storage import Post, Comment, SubredditMeta, ContentType, Tier, Database
from karmaforge.llm import LLMClient, LLMConfig, LLMProvider


@pytest.fixture
def sample_posts() -> list[Post]:
    posts = []
    base_time = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)

    fixtures = [
        # (title, body, subreddit, upvotes, content_type, flair, tier)
        ("I just discovered this one weird trick for productivity — it changed everything",
         "After years of struggling with procrastination, I finally found something that works. "
         "The key insight is that most productivity systems overcomplicate things. "
         "Here's the simple 3-step process I use now:\n\n"
         "1. Write down your top 3 priorities the night before\n"
         "2. Do the hardest one first, before checking any messages\n"
         "3. Take a 10-minute break every 90 minutes\n\n"
         "I've been doing this for 6 months and my output has doubled. Has anyone else tried something similar?",
         "productivity", 2500, ContentType.TEXT, "Tips & Tricks", Tier.T2),

        ("PSA: Reddit's new API pricing is going to kill third-party apps",
         "I've been a Reddit developer for 5 years and this is the worst change I've seen. "
         "The new pricing is $0.24 per 1000 requests, which might not sound like much but it adds up fast. "
         "Apollo, the most popular iOS Reddit app, would need to pay $20M/year.\n\n"
         "What do you think this means for the future of Reddit?",
         "technology", 15000, ContentType.TEXT, "Discussion", Tier.T2),

        ("After 10 years of weightlifting, here's what nobody tells you about form",
         "TL;DR: Perfect form is a myth. What matters is consistent, safe progression.\n\n"
         "I've spent a decade in the gym and competed at national level. "
         "The biggest lesson I learned is that chasing 'perfect form' actually held me back.\n\n"
         "Here's what actually matters: consistency over perfection. Controlled progression. "
         "Listening to your body instead of copying YouTube videos.\n\n"
         "Let me know your thoughts below.",
         "Fitness", 3200, ContentType.TEXT, "Tips", Tier.T2),

        ("Unpopular opinion: Most SaaS startups fail because they launch too late, not too early",
         "Everyone says 'validate before you build' but I've seen the opposite kill more companies. "
         "By the time you've validated, someone else has shipped.\n\n"
         "My SaaS hit $10k MRR in 4 months because we shipped a broken MVP and fixed it in public. "
         "The first 10 users gave us more useful feedback than 100 survey responses.",
         "SaaS", 850, ContentType.TEXT, "Discussion", Tier.T3),

        ("I built a free tool that automates Kubernetes debugging — here's how it works",
         "GitHub link in comments.\n\n"
         "After spending 40% of my work hours debugging k8s issues, I built a CLI tool that "
         "automatically detects common problems and suggests fixes.\n\n"
         "It checks: pod scheduling, resource limits, network policies, ingress config, and more. "
         "Open source under MIT license. Would love feedback from the community!",
         "kubernetes", 620, ContentType.TEXT, "Resource", Tier.T3),

        ("[Image] My 3-year progress from absolute beginner to professional artist",
         "",
         "pics", 12000, ContentType.IMAGE, "Artwork", Tier.T1),

        ("What's the one life hack that actually changed your daily routine?",
         "I'm always skeptical of 'life hacks' but every now and then one actually sticks. "
         "For me it was putting my phone in another room before bed. Sleep quality improved dramatically.\n\n"
         "Curious what has actually worked for other people long-term?",
         "AskReddit", 5000, ContentType.TEXT, None, Tier.T1),

        ("ELI5: Why does inflation happen and why can't governments just print more money?",
         "I know this is probably a basic economics question but I genuinely don't understand "
         "the mechanism behind inflation. If the government needs money, why can't they just print it? "
         "What actually happens when they do?",
         "explainlikeimfive", 8000, ContentType.TEXT, None, Tier.T1),

        ("X vs Y: Notion vs Obsidian for knowledge management — honest comparison after 2 years with both",
         "I've used Notion for 2 years (team projects) and Obsidian for 18 months (personal notes). "
         "Here's my honest breakdown:\n\n"
         "**Notion wins:** Collaboration, databases, templates, web clipper\n"
         "**Obsidian wins:** Speed, offline access, local files, graph view, plugin ecosystem\n\n"
         "Bottom line: use Notion for team wikis, Obsidian for personal knowledge bases. "
         "They're complementary, not competitors.",
         "productivity", 1800, ContentType.TEXT, "Comparison", Tier.T2),

        ("My journey from $0 to $5k MRR as a solo developer — full breakdown",
         "It took me 18 months to go from idea to sustainable income. Here's exactly what happened:\n\n"
         "Month 1-3: Built 3 failed products (learned what NOT to build)\n"
         "Month 4: Launched a Chrome extension (50 users, $0)\n"
         "Month 5-8: Pivoted to SaaS based on extension user feedback\n"
         "Month 9-12: Grew to $1k MRR through cold outreach\n"
         "Month 13-18: Content marketing took us to $5k\n\n"
         "Full revenue breakdown and lessons learned in comments. AMA!",
         "SaaS", 1100, ContentType.TEXT, "AMA", Tier.T3),
    ]

    for i, (title, body, sub, upvotes, ct, flair, tier) in enumerate(fixtures):
        posts.append(Post(
            post_id=f"t3_test{i:04d}",
            subreddit=sub,
            title=title,
            body=body,
            author=f"test_user_{i}",
            created_utc=base_time,
            upvotes=upvotes,
            upvote_ratio=0.85 + (i * 0.01),
            num_comments=int(upvotes * 0.1),
            content_type=ct,
            flair=flair,
            source_dataset="test",
            tier=tier,
        ))

    return posts


@pytest.fixture
def sample_comments(sample_posts) -> list[Comment]:
    comments = []
    for i, post in enumerate(sample_posts[:5]):
        for j in range(5):
            comments.append(Comment(
                comment_id=f"t1_test{i}_{j}",
                post_id=post.post_id,
                parent_id=post.post_id,
                body=f"Test comment {j} on post {i}. This is a sample comment with some discussion content.",
                author=f"commenter_{i}_{j}",
                created_utc=post.created_utc,
                upvotes=10 - j,
                depth=j % 3,
                thread_root_id=f"t1_test{i}_0" if j > 0 else None,
            ))
    return comments


@pytest.fixture
def mock_llm_client() -> MagicMock:
    mock = MagicMock(spec=LLMClient)
    mock.complete.return_value = "test response"
    mock.classify.side_effect = lambda texts, *args, **kwargs: ["counterintuitive_discovery"] * len(texts)
    mock.analyze_sentiment.side_effect = lambda texts, *args, **kwargs: [{"polarity": "neutral", "intensity": 0.5}] * len(texts)
    return mock


@pytest.fixture
def temp_db(sample_posts) -> Database:
    db_path = Path(tempfile.mktemp(suffix=".db"))
    db = Database(db_path)
    db.create_schema()
    if sample_posts:
        db.insert_posts(sample_posts)
    return db
