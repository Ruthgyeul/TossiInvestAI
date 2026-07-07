"""Gemini Free Tier — 뉴스 요약 테스트 (docs/BIN.md)."""

import pytest

import core.gateway.gemini as gemini_module
from core.gateway.gemini import gemini_gateway


class _FakeResponse:
    def __init__(self, text: str | None) -> None:
        self.text = text


class _Captured:
    model: str | None = None
    contents: str | None = None


async def _fake_generate_content(model: str, contents: str) -> _FakeResponse:
    _Captured.model = model
    _Captured.contents = contents
    return _FakeResponse("  삼성전자 3분기 실적 호조 전망, 반도체 업황 개선 기대  ")


@pytest.mark.asyncio
async def test_summarize_news_returns_stripped_gemini_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gemini_module._client.aio.models, "generate_content", _fake_generate_content)

    result = await gemini_gateway.summarize_news(
        ["삼성전자, 3분기 영업이익 컨센서스 상회", "반도체 업황 개선 신호"]
    )

    assert result == "삼성전자 3분기 실적 호조 전망, 반도체 업황 개선 기대"
    assert _Captured.model == gemini_module.settings.GEMINI_MODEL
    assert "삼성전자, 3분기 영업이익 컨센서스 상회" in _Captured.contents
    assert "반도체 업황 개선 신호" in _Captured.contents


@pytest.mark.asyncio
async def test_summarize_news_raises_value_error_when_response_text_is_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_generate_content_no_text(model: str, contents: str) -> _FakeResponse:
        return _FakeResponse(None)

    monkeypatch.setattr(
        gemini_module._client.aio.models, "generate_content", _fake_generate_content_no_text
    )

    with pytest.raises(ValueError, match="Gemini 응답에 text가 없음"):
        await gemini_gateway.summarize_news(["삼성전자, 3분기 영업이익 컨센서스 상회"])


@pytest.mark.asyncio
async def test_summarize_news_returns_empty_string_for_no_articles() -> None:
    result = await gemini_gateway.summarize_news([])

    assert result == ""


@pytest.mark.asyncio
async def test_decide_is_not_supported() -> None:
    with pytest.raises(NotImplementedError):
        await gemini_gateway.decide(state=None)  # type: ignore[arg-type]
