"""Gemini Free Tier — 뉴스 요약 테스트 (docs/BIN.md)."""

import pytest

import core.gateway.gemini as gemini_module
from core.gateway.gemini import gemini_gateway


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeGenerativeModel:
    captured_model_name: str | None = None
    captured_prompt: str | None = None

    def __init__(self, model_name: str) -> None:
        _FakeGenerativeModel.captured_model_name = model_name

    async def generate_content_async(self, prompt: str) -> _FakeResponse:
        _FakeGenerativeModel.captured_prompt = prompt
        return _FakeResponse("  삼성전자 3분기 실적 호조 전망, 반도체 업황 개선 기대  ")


@pytest.mark.asyncio
async def test_summarize_news_returns_stripped_gemini_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gemini_module.genai, "GenerativeModel", _FakeGenerativeModel)

    result = await gemini_gateway.summarize_news(
        ["삼성전자, 3분기 영업이익 컨센서스 상회", "반도체 업황 개선 신호"]
    )

    assert result == "삼성전자 3분기 실적 호조 전망, 반도체 업황 개선 기대"
    assert _FakeGenerativeModel.captured_model_name == gemini_module.settings.GEMINI_MODEL
    assert "삼성전자, 3분기 영업이익 컨센서스 상회" in _FakeGenerativeModel.captured_prompt
    assert "반도체 업황 개선 신호" in _FakeGenerativeModel.captured_prompt


@pytest.mark.asyncio
async def test_summarize_news_returns_empty_string_for_no_articles() -> None:
    result = await gemini_gateway.summarize_news([])

    assert result == ""


@pytest.mark.asyncio
async def test_decide_is_not_supported() -> None:
    with pytest.raises(NotImplementedError):
        await gemini_gateway.decide(state=None)  # type: ignore[arg-type]
