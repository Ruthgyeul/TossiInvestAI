"""토스증권 OAuth2 토큰 발급·갱신. Redis `token:toss` 키로 캐시하고 만료 5분 전 자동 갱신 (docs/TOSS_API.md)."""


async def get_access_token() -> str:
    """캐시된 토큰이 유효하면 반환하고, 아니면 재발급한다."""
    raise NotImplementedError


async def _issue_token() -> str:
    """POST /oauth2/token — grant_type=client_credentials."""
    raise NotImplementedError
