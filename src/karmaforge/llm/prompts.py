"""Prompt templates for LLM-based analysis tasks.

Separated from client.py so prompts can be iterated on without touching API code.
"""

HOOK_TYPE_CLASSIFY = """Classify the following Reddit post title into exactly one hook type.

Categories:
- counterintuitive_discovery: "I just discovered X...", "X changed everything", unexpected findings
- suspense_mystery: Cliffhangers, "you won't believe what happened", unresolved tension
- pain_point: Addresses a common frustration, problem, or annoyance
- identity_label: Appeals to a specific identity/group ("as a developer...", "if you're a parent...")
- number_shock: Uses specific numbers to grab attention ("10 things...", "$50,000 in 3 months")
- story_opener: Begins a personal narrative ("My journey...", "After 5 years of...")
- resource_share: Offers a tool, guide, or resource ("[Resource] I built...", "Free template for...")
- controversial_opinion: "Unpopular opinion:", "Hot take:", deliberately provocative
- comparison_analysis: "X vs Y", side-by-side comparisons
- curious_question: "ELI5:", "Why does X?", "Has anyone else...", genuine curiosity

Title: {title}

Return only the category name, nothing else. Do not add punctuation or explanation."""

NARRATIVE_MODE_CLASSIFY = """Classify the following Reddit post body into exactly one narrative mode.

Categories:
- story_personal: First-person personal experience, anecdote, or journey
- tutorial_howto: Step-by-step guide, instructions, educational content
- opinion_argument: Stated opinion, argument, or persuasive essay
- question_discussion: Open-ended question to the community
- resource_showcase: Sharing a tool, website, or resource (often with link)
- news_event: Reporting news, current events, or external happenings
- humor_satire: Joke, meme, or satirical content
- review_critique: Product review, media critique, or analysis

Post body excerpt (first 500 chars):
{body}

Return only the category name, nothing else."""

OPENING_PATTERN_CLASSIFY = """Classify the opening pattern of this Reddit post body.

Categories:
- hook_first: Starts with an attention-grabbing statement or surprising fact
- background_first: Starts with context, backstory, or explanation
- conflict_first: Starts with a problem, tension, or challenge
- personal_intro: Starts with "I am...", "A bit about me..."
- direct_answer: Jumps straight into answering or explaining
- rhetorical_question: Opens with a question to the reader
- quote_reference: Opens with a quote or external reference

Post body opening (first 200 chars):
{body}

Return only the category name, nothing else."""

SENTIMENT_ANALYZE = """Analyze the sentiment of this Reddit post title.

Return a JSON object with exactly these keys:
- polarity: "positive", "negative", or "neutral"
- intensity: A number from 0.0 to 1.0 indicating how strong the sentiment is
- emotion: The primary emotion (e.g., "excitement", "anger", "curiosity", "frustration", "gratitude", "surprise", "nostalgia")

Title: {title}

Return only valid JSON, nothing else."""

PATTERN_SUMMARIZE = """Summarize the following viral content pattern based on the cluster of posts below.

Give the pattern:
1. A short, catchy name (like "The Counterintuitive Discovery" or "The Expert Reveal")
2. A 2-3 sentence description of what makes this pattern work
3. A title formula with {variable} placeholders
4. A body structure outline (section by section)

Cluster characteristics:
- Hook type: {hook_type}
- Narrative mode: {narrative_mode}
- Average upvotes: {avg_upvotes}
- Viral rate: {viral_rate}%
- Typical subreddits: {subreddits}

Example titles from this cluster:
{titles}

Example body openings from this cluster:
{bodies}

Return a JSON object with keys: name, description, title_formula, body_structure.
The body_structure should be a list of section descriptions."""

IMAGE_CONTENT_CLASSIFY = """Based on the post title and any available URL patterns, classify what type of visual content this Reddit post likely contains.

Categories:
- screenshot: Screenshot of text, code, social media, or UI
- infographic: Data visualization, chart, or designed informational graphic
- meme: Meme image with text overlay
- photo: Original photograph or picture
- diagram: Technical diagram, flowchart, or illustration
- none: No image, or URL pattern suggests text-only post

Title: {title}
URL (if available): {url}

Return only the category name, nothing else."""

WHY_IT_FAILED = """Analyze why this Reddit post likely failed to gain traction.

Post details:
- Title: {title}
- Body excerpt: {body}
- Subreddit: {subreddit}
- Upvotes: {upvotes}
- Upvote ratio: {upvote_ratio}
- Comments: {num_comments}
- Posted: {created_utc}
- Flair: {flair}

Compared to the viral baseline for r/{subreddit}:
{viral_baseline}

Give a concise diagnosis (1-2 sentences) of the most likely reason this post underperformed.
Focus on actionable issues: title weakness, wrong timing, mismatch with subreddit, poor structure, etc.
Do NOT say "the content wasn't interesting" — be specific."""


# ── v2 Generator prompts ──────────────────────────────────────────

TITLE_GENERATE = """Generate a Reddit post title based on the following viral pattern.

Pattern: {pattern_name}
Pattern description: {pattern_description}
Hook type: {hook_type}

User's topic: {user_topic}
Target subreddit: r/{subreddit}
Subreddit style notes: {subreddit_notes}

Title constraints:
- Word count: {min_words}-{max_words} words
- Must use the {hook_type} hook style authentically
- Must NOT sound like clickbait or AI-generated
- Must provide real value or genuine insight to readers
Generate exactly ONE title. Return only the title text, nothing else. No quotes, no prefixes."""

BODY_GENERATE = """Write a Reddit post body based on the following specifications.

Title: {title}
Pattern: {pattern_name}
Hook type: {hook_type}
Narrative mode: {narrative_mode}
Body structure guidance: {body_structure}

Target subreddit: r/{subreddit}
Subreddit style notes: {subreddit_notes}

Constraints:
- Word count: {min_words}-{max_words} words
- Readability: target Flesch Reading Ease between {target_readability_min}-{target_readability_max}
- Start with a strong opening that matches the {hook_type} hook
- {structure_requirements}
- End with a genuine question or call for discussion (not forced)
- Be authentic and personal, not AI-sounding
- Format naturally with paragraphs — no markdown headers, no "TL;DR" unless it fits the subreddit style
Post body:"""

TITLE_VALIDATE = """Evaluate this Reddit post title objectively.

Title: "{title}"
Target subreddit: r/{subreddit}
Target word count range: {min_words}-{max_words} words
Expected hook type: {expected_hook_type}

Rate each dimension from 0-100:
1. hook_clarity — is the hook type clearly present?
2. word_count_fit — does it fall within the target range?
3. authenticity — does it sound like a real person wrote it?
4. curiosity_gap — does it make readers want to click?
5. value_promise — does it imply genuine value inside?

Known anti-patterns to watch for: {anti_patterns}

Return a JSON object with these exact keys:
- scores: {{"hook_clarity": N, "word_count_fit": N, "authenticity": N, "curiosity_gap": N, "value_promise": N}}
- word_count: actual word count
- anti_patterns_triggered: list of anti-pattern names triggered
- overall_score: weighted average of the 5 scores
- suggestion: if any dimension scores below 50, suggest improvement (else empty string)

Return only valid JSON, nothing else."""

BODY_REVISE = """Revise the following Reddit post body to fix the identified quality issues.

Title: {title}
Current body:
{body}

Issues that MUST be fixed:
{suggestions}

Target subreddit: r/{subreddit}

Guidelines:
- Fix ONLY the identified issues — keep everything else intact
- Keep the same overall topic and voice
- Be authentic and personal, not AI-sounding
- Maintain natural paragraph breaks
- Do NOT add markdown headers or TL;DR sections unless the original had them

Return only the revised body text, nothing else. No quotes, no prefixes, no explanations."""

FAILURE_ATTRIBUTE_V2 = """Analyze why this Reddit post underperformed. Reply in Chinese (中文).

Post details:
- Title: {title}
- Body excerpt: {body_excerpt}
- Subreddit: r/{subreddit}
- Actual upvotes: {actual_upvotes}
- Upvote ratio: {upvote_ratio}
- Comments: {num_comments}
- Posted at: {posted_at}
- Recommended posting time: {recommended_time}

Expected pattern: {pattern_name}
Pattern historical viral rate: {viral_rate}%
Pattern avg upvotes: {avg_upvotes}

Subreddit median upvotes: {subreddit_median}

Diagnose the most likely failure reasons:
1. Title mismatch with pattern's hook type
2. Body structure deviation from pattern
3. Posting time vs subreddit optimal window
4. Topic relevance to subreddit audience
5. Content quality (too short/long, readability, depth)

Return a JSON object (all values in Chinese):
- primary_reason: 最重要的失败原因 (1 sentence in Chinese)
- secondary_reasons: 1-2 个辅助因素 (list of Chinese strings)
- action_items: 1-3 条具体改进建议 (list of Chinese strings)
- confidence: 0-100 对此诊断的信心程度

Return only valid JSON, nothing else."""
