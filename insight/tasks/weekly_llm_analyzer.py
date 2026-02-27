import json
import logging
from typing import Any

from insight.tasks.prompts import (
    USER_SYS_PROM,
    USER_TREND_PROM,
    WEEKLY_SYS_PROM,
    WEEKLY_TREND_PROM,
)
from modules.llm.openai.client import OpenAIClient

logger = logging.getLogger("newsletter")


def _generate_analysis(
    posts: list,
    user_prompt: str,
    sys_prompt: str,
    api_key: str,
) -> dict[str, Any]:
    """공통 분석 로직"""
    client = OpenAIClient.get_client(api_key)
    prompt = user_prompt.format(posts=posts, count=len(posts))

    logger.info("Generated prompt:\n%s", prompt)

    try:
        result = client.generate_text(
            prompt=prompt,
            system_prompt=sys_prompt,
            temperature=0.1,
            response_format={"type": "json_object"},
        )

        logger.info("LLM raw result:\n%s", result)

        if isinstance(result, str):
            result = json.loads(result)

        return result
    except Exception as e:
        logger.error("Failed to generate analysis: %s", e)
        raise


def analyze_trending_posts(posts: list, api_key: str) -> dict[str, Any]:
    return _generate_analysis(
        posts, WEEKLY_TREND_PROM, WEEKLY_SYS_PROM, api_key
    )


def analyze_user_posts(posts: list, api_key: str) -> dict[str, Any]:
    return _generate_analysis(posts, USER_TREND_PROM, USER_SYS_PROM, api_key)
