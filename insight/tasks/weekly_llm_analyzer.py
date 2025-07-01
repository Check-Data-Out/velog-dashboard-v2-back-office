import logging

from prompts import SYS_PROM, USER_TREND_PROM, WEEKLY_TREND_PROM

from modules.llm.base_client import LLMClient
from modules.llm.openai.client import OpenAIClient

logger = logging.getLogger("scraping")


def analyze_trending_posts(posts: list, api_key: str) -> dict:
    client: LLMClient = OpenAIClient.get_client(api_key)
    prompt = WEEKLY_TREND_PROM.format(posts=posts)

    logger.info("Generated weekly trend prompt:\n%s", prompt)

    try:
        result = client.generate_text(
            prompt=prompt,
            system_prompt=SYS_PROM,
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        return result
    except Exception as e:
        logger.error("Failed to analyze_trending_posts : %s", e)
        raise


def analyze_user_posts(posts: list, api_key: str) -> dict:
    client: LLMClient = OpenAIClient.get_client(api_key)
    prompt = USER_TREND_PROM.format(posts=posts)

    logger.info("Generated user trend prompt:\n%s", prompt)

    try:
        result = client.generate_text(
            prompt=prompt,
            system_prompt=SYS_PROM,
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        return result
    except Exception as e:
        logger.error("Failed to analyze_user_posts : %s", e)
        raise
