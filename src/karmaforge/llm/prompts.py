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
