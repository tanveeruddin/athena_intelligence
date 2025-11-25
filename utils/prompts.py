"""
LLM prompt templates for analysis and evaluation.
Contains structured prompts for Gemini API calls.
"""

from typing import Dict, Any, List


# ============================================================================
# ANALYSIS PROMPTS
# ============================================================================

ANNOUNCEMENT_ANALYSIS_SYSTEM_PROMPT = """You are an expert financial analyst specializing in Australian Securities Exchange (ASX) announcements.

Your task is to analyze ASX announcements and extract:
1. A concise 2-3 sentence executive summary
2. Sentiment classification (BULLISH, BEARISH, or NEUTRAL)
3. 3-5 key insights for investors
4. Management promises or commitments (with specific targets/dates if mentioned)
5. Financial impact assessment

Be objective, precise, and focus on material information that would affect investment decisions.
"""


def get_announcement_analysis_prompt(markdown_content: str, company_name: str, asx_code: str) -> str:
    """
    Generate analysis prompt for an announcement.

    Args:
        markdown_content: Announcement content in markdown format
        company_name: Full company name
        asx_code: ASX ticker code

    Returns:
        Formatted prompt string
    """
    return f"""Analyze the following ASX announcement for {company_name} ({asx_code}):

ANNOUNCEMENT CONTENT:
{markdown_content}

Provide your analysis in the following JSON format:
{{
  "summary": "2-3 sentence executive summary",
  "sentiment": "BULLISH or BEARISH or NEUTRAL",
  "key_insights": [
    "First key insight",
    "Second key insight",
    "Third key insight"
  ],
  "management_promises": [
    "Specific commitment 1 (with target/date if mentioned)",
    "Specific commitment 2 (with target/date if mentioned)"
  ],
  "financial_impact": "Brief assessment of potential financial impact"
}}

IMPORTANT:
- Sentiment BULLISH: Positive news, growth, improved performance, strong results
- Sentiment BEARISH: Negative news, losses, warnings, declining performance
- Sentiment NEUTRAL: Administrative, procedural, or mixed signals
- Key insights should be actionable for investors
- Management promises must be specific and verifiable
- Return ONLY valid JSON, no additional text
"""


# ============================================================================
# TIMELINE COMPARISON PROMPTS
# ============================================================================

TIMELINE_ANALYSIS_SYSTEM_PROMPT = """You are an expert financial analyst specializing in trend analysis and performance tracking.

Your task is to analyze a company's announcement timeline to identify:
1. Performance trends over time (improving, stable, or declining)
2. Promise fulfillment (are commitments being kept?)
3. Strategic direction changes
4. Consistency in execution

Provide quantitative scores and clear evidence for your assessments.
"""


def get_timeline_comparison_prompt(
    company_name: str,
    asx_code: str,
    historical_announcements: List[Dict[str, Any]],
    new_announcement: Dict[str, Any]
) -> str:
    """
    Generate timeline comparison prompt.

    Args:
        company_name: Full company name
        asx_code: ASX ticker code
        historical_announcements: List of historical announcement summaries
        new_announcement: New announcement data

    Returns:
        Formatted prompt string
    """
    # Format historical timeline
    timeline_text = ""
    for i, ann in enumerate(historical_announcements, 1):
        timeline_text += f"\n{i}. Date: {ann.get('event_date', 'N/A')}\n"
        timeline_text += f"   Summary: {ann.get('summary', 'N/A')}\n"
        timeline_text += f"   Sentiment: {ann.get('sentiment', 'N/A')}\n"
        if ann.get('management_promises'):
            timeline_text += f"   Promises: {ann.get('management_promises')}\n"

    return f"""Analyze the announcement timeline for {company_name} ({asx_code}):

HISTORICAL ANNOUNCEMENTS (chronological order):
{timeline_text}

LATEST ANNOUNCEMENT:
Date: {new_announcement.get('event_date', 'N/A')}
Summary: {new_announcement.get('summary', 'N/A')}
Sentiment: {new_announcement.get('sentiment', 'N/A')}
Promises: {new_announcement.get('management_promises', [])}

ANALYSIS TASKS:
1. Performance Trend: Is the company's performance IMPROVING, STABLE, or DECLINING?
2. Promise Fulfillment: Are previous commitments being kept? What's the evidence?
3. Strategic Direction: Any significant strategic shifts evident?
4. Quantitative Scores:
   - Improvement Score: -1.0 (significant decline) to +1.0 (significant improvement)
   - Consistency Score: 0.0 (chaotic/unpredictable) to 1.0 (highly consistent)
   - Promise Fulfillment Score: 0.0 (broken promises) to 1.0 (all fulfilled)

Provide your analysis in the following JSON format:
{{
  "performance_trend": "IMPROVING or STABLE or DECLINING",
  "improvement_score": 0.5,
  "consistency_score": 0.8,
  "promise_fulfillment_score": 0.7,
  "analysis_summary": "2-3 sentence summary of trends and patterns",
  "promise_tracking": [
    {{
      "promise": "Original commitment text",
      "date_made": "2025-08-15",
      "status": "ON_TRACK or FULFILLED or BROKEN",
      "evidence": "Supporting evidence from announcements"
    }}
  ],
  "strategic_shifts": "Any notable changes in strategy or focus"
}}

Return ONLY valid JSON, no additional text.
"""


# ============================================================================
# EVALUATION PROMPTS (LLM-as-a-Judge)
# ============================================================================

EVALUATION_SYSTEM_PROMPT = """You are an expert evaluator assessing the quality of financial announcement analysis.

Evaluate on these criteria:
1. Summary Accuracy: Does it capture the key points? Is it concise yet complete?
2. Sentiment Correctness: Is the sentiment classification appropriate?
3. Insight Quality: Are insights actionable, relevant, and well-supported?

Provide scores (1-5 scale) and constructive feedback.
"""


def get_evaluation_prompt(
    original_content: str,
    generated_summary: str,
    generated_sentiment: str,
    generated_insights: List[str]
) -> str:
    """
    Generate LLM-as-a-Judge evaluation prompt.

    Args:
        original_content: Original announcement text
        generated_summary: AI-generated summary
        generated_sentiment: AI-generated sentiment
        generated_insights: AI-generated insights

    Returns:
        Formatted prompt string
    """
    insights_text = "\n".join([f"- {insight}" for insight in generated_insights])

    return f"""Evaluate the quality of this financial announcement analysis:

ORIGINAL ANNOUNCEMENT (first 1000 chars):
{original_content[:1000]}...

GENERATED ANALYSIS:
Summary: {generated_summary}
Sentiment: {generated_sentiment}
Key Insights:
{insights_text}

EVALUATION CRITERIA:

1. Summary Accuracy (1-5):
   - 5: Captures all key points concisely, no important information missed
   - 4: Captures most key points, minor omissions
   - 3: Adequate but misses some important details
   - 2: Significant omissions or inaccuracies
   - 1: Poor summary, misses critical information

2. Sentiment Correctness (1-5):
   - 5: Perfectly appropriate sentiment classification
   - 4: Generally correct, minor nuance missed
   - 3: Debatable but defensible
   - 2: Questionable classification
   - 1: Clearly incorrect sentiment

3. Insight Quality (1-5):
   - 5: Highly actionable, well-supported, investor-focused insights
   - 4: Good insights with minor improvements possible
   - 3: Adequate but generic or not fully actionable
   - 2: Weak insights, limited value
   - 1: Poor quality, irrelevant, or misleading

Provide your evaluation in the following JSON format:
{{
  "summary_score": 4,
  "summary_feedback": "Brief explanation of score",
  "sentiment_score": 5,
  "sentiment_feedback": "Brief explanation of score",
  "insights_score": 4,
  "insights_feedback": "Brief explanation of score",
  "overall_score": 4.3,
  "overall_feedback": "Overall assessment and improvement suggestions"
}}

Return ONLY valid JSON, no additional text.
"""


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def truncate_content(content: str, max_length: int = 4000) -> str:
    """
    Truncate content to fit within token limits.

    Args:
        content: Content to truncate
        max_length: Maximum character length

    Returns:
        Truncated content
    """
    if len(content) <= max_length:
        return content

    return content[:max_length] + "\n\n[Content truncated for length...]"


def format_json_response(response_text: str) -> str:
    """
    Clean up LLM response to extract JSON.

    Args:
        response_text: Raw LLM response

    Returns:
        Cleaned JSON string
    """
    # Remove markdown code blocks if present
    text = response_text.strip()

    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]

    if text.endswith("```"):
        text = text[:-3]

    return text.strip()


# ============================================================================
# TRADING DECISION PROMPTS (Human-in-the-Loop)
# ============================================================================

TRADING_DECISION_SYSTEM_PROMPT = """You are an expert financial analyst and trading advisor with deep knowledge of the Australian Securities Exchange (ASX).

Your task is to analyze comprehensive data about a company's ASX announcement and provide a trading recommendation (BUY, SELL, or HOLD).

Consider ALL available information:
1. **Sentiment Analysis**: Overall tone, confidence, and key points from the announcement
2. **Stock Performance**: Current price, historical trends (1M/3M/6M changes)
3. **Timeline Analysis**: Company improvement over time, consistency, promise fulfillment
4. **Content Quality**: Summary accuracy, sentiment correctness, insights quality
5. **Management Promises**: Track record of delivering on commitments
6. **Market Context**: Industry trends and comparative performance

IMPORTANT Decision Criteria:
- **BUY**: Strong positive signals across multiple dimensions, high confidence in growth
- **SELL**: Significant negative signals, deteriorating performance, broken promises
- **HOLD**: Mixed signals, insufficient confidence, or wait-and-see situation

Be conservative and risk-aware. Only recommend BUY/SELL with strong supporting evidence.
Provide clear reasoning that a human can verify and understand.
"""


def get_trading_decision_prompt(
    company_name: str,
    asx_code: str,
    current_price: float,
    summary: str,
    sentiment: str,
    sentiment_confidence: float,
    insights: List[str],
    promises: List[Dict[str, Any]],
    improvement_score: int = None,
    consistency_score: int = None,
    promise_fulfillment_score: int = None,
    sentiment_trend: str = None,
    strategic_shifts: List[str] = None,
    overall_score: float = None,
    summary_score: int = None,
    sentiment_score: int = None,
    insights_score: int = None,
    month_1_change: float = None,
    month_3_change: float = None,
    month_6_change: float = None,
) -> str:
    """
    Generate trading decision prompt with comprehensive data.

    Args:
        company_name: Full company name
        asx_code: ASX ticker code
        current_price: Current stock price
        summary: Analysis summary
        sentiment: Sentiment classification
        sentiment_confidence: Confidence in sentiment
        insights: Key insights list
        promises: Management promises
        improvement_score: Timeline improvement (0-10)
        consistency_score: Timeline consistency (0-10)
        promise_fulfillment_score: Promise fulfillment (0-10)
        sentiment_trend: Sentiment trend over time
        strategic_shifts: Strategic changes identified
        overall_score: Overall evaluation score (0-5)
        summary_score: Summary quality (0-5)
        sentiment_score: Sentiment accuracy (0-5)
        insights_score: Insights quality (0-5)
        month_1_change: 1-month price change %
        month_3_change: 3-month price change %
        month_6_change: 6-month price change %

    Returns:
        Formatted prompt string
    """
    # Format insights
    insights_text = "\n".join([f"  • {i}" for i in insights]) if insights else "  None available"

    # Format promises
    promises_text = ""
    if promises:
        for p in promises:
            if isinstance(p, dict):
                promises_text += f"  • {p.get('promise', str(p))}\n"
            else:
                promises_text += f"  • {p}\n"
    else:
        promises_text = "  None available"

    # Format strategic shifts
    shifts_text = "\n".join([f"  • {s}" for s in strategic_shifts]) if strategic_shifts else "  None identified"

    # Format price changes with signs
    def format_change(change):
        if change is None:
            return "N/A"
        sign = "+" if change > 0 else ""
        return f"{sign}{change:.2f}%"

    return f"""Analyze this comprehensive data for {company_name} ({asx_code}) and provide a trading recommendation:

═══════════════════════════════════════════════════════════
📊 CURRENT STOCK INFORMATION
═══════════════════════════════════════════════════════════
Current Price: ${current_price:.2f}

Stock Performance:
  • 1 Month:  {format_change(month_1_change)}
  • 3 Months: {format_change(month_3_change)}
  • 6 Months: {format_change(month_6_change)}

═══════════════════════════════════════════════════════════
📰 LATEST ANNOUNCEMENT ANALYSIS
═══════════════════════════════════════════════════════════
Sentiment: {sentiment} (Confidence: {sentiment_confidence*100:.1f}%)

Executive Summary:
{summary}

Key Insights:
{insights_text}

Management Promises:
{promises_text}

═══════════════════════════════════════════════════════════
📈 TIMELINE ANALYSIS (Historical Performance)
═══════════════════════════════════════════════════════════
Improvement Score:      {improvement_score if improvement_score is not None else 'N/A'}/10
Consistency Score:      {consistency_score if consistency_score is not None else 'N/A'}/10
Promise Fulfillment:    {promise_fulfillment_score if promise_fulfillment_score is not None else 'N/A'}/10
Sentiment Trend:        {sentiment_trend or 'N/A'}

Strategic Shifts:
{shifts_text}

═══════════════════════════════════════════════════════════
✅ ANALYSIS QUALITY SCORES
═══════════════════════════════════════════════════════════
Overall Quality:  {overall_score if overall_score is not None else 'N/A'}/5
Summary Score:    {summary_score if summary_score is not None else 'N/A'}/5
Sentiment Score:  {sentiment_score if sentiment_score is not None else 'N/A'}/5
Insights Score:   {insights_score if insights_score is not None else 'N/A'}/5

═══════════════════════════════════════════════════════════
🎯 YOUR TASK
═══════════════════════════════════════════════════════════
Based on this comprehensive analysis, provide a trading recommendation.

Consider:
1. Is the sentiment supported by concrete evidence?
2. Are stock price trends aligned with company performance?
3. Is the company consistently improving or deteriorating?
4. Is management delivering on promises?
5. Are there any red flags or exceptional opportunities?
6. What is the risk-reward profile?

Provide your recommendation in the following JSON format:
{{
  "decision": "BUY" | "SELL" | "HOLD",
  "confidence_score": 0.85,
  "reasoning": "Detailed explanation of your decision covering key factors",
  "key_factors": [
    "Most important factor supporting this decision",
    "Second most important factor",
    "Third most important factor"
  ],
  "risks": [
    "Primary risk to consider",
    "Secondary risk to consider"
  ],
  "short_term_outlook": "POSITIVE" | "NEUTRAL" | "NEGATIVE",
  "long_term_outlook": "POSITIVE" | "NEUTRAL" | "NEGATIVE"
}}

CRITICAL INSTRUCTIONS:
- Be conservative: Only BUY/SELL with confidence_score >= 0.7
- If confidence < 0.7, recommend HOLD
- Reasoning must be specific and evidence-based
- Key factors must reference actual data provided above
- Risks must be realistic and specific to this company
- Return ONLY valid JSON, no additional text
"""
