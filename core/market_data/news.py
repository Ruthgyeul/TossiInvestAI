"""뉴스 파싱·캐싱. 요약은 Gemini Gateway에 위임한다 (docs/BIN.md)."""

from core.gateway.gemini import gemini_gateway


async def fetch_news(symbol: str) -> list[str]:
    raise NotImplementedError


async def get_news_summary(symbol: str) -> str:
    articles = await fetch_news(symbol)
    return await gemini_gateway.summarize_news(articles)
