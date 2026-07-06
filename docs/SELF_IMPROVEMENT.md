# SELF_IMPROVEMENT.md — 자기개선 루프

> 빈(Bin)은 스스로를 관찰하고 개선안을 제안할 수 있지만,
> **안전·자금 관련 규칙을 스스로 바꾸거나, 검증 없이 실전에 반영할 수는 없다.**
> 이 문서는 Reflection → 개선 후보 도출 → 백테스트 검증 → 개발자 승인 → 배포·롤백
> 으로 이어지는 자기개선 파이프라인을 정의한다.

---

## 원칙

1. 모든 개선은 **제안(propose)** 까지만 자동화된다. 실전 배포는 항상 개발자 승인을 거친다.
2. 개선 후보는 배포 전 반드시 `core/strategy/backtest.py`로 검증한다 (최소 1Y).
3. `docs/SAFETY.md`의 Safety Gate 조건, `INITIAL_SEED_KRW`, 자금 배분 비율(`CASH_BUFFER_RATIO` 등)은
   자기개선 루프의 대상이 아니다 — 코드로 자동 변경 금지 (CLAUDE.md 절대 규칙 3, 10).
4. 모든 변경은 `strategy_version` / `prompt_version`으로 추적되며, 이전 버전으로 즉시 롤백 가능해야 한다.

---

## 자기개선 루프 개요

```
장 마감 후 Reflection (docs/BIN.md)
    │  KR 15:40 / US 06:10 (KST), Claude 1회 호출
    ▼
개선 후보 추출
    ├── 반복적으로 놓친 매수/매도 패턴
    ├── 반복적으로 틀린 판단 (confidence 높았지만 손실)
    ├── Safety Gate 거부 중 과도하게 보수적이었던 조건
    └── 프롬프트 설명 부족으로 오판된 사례
    ▼
개선안 초안 생성 (프롬프트 문구 수정 / 전략 파라미터 조정)
    │  reflections 테이블에 proposed_change 필드로 저장
    ▼
core/strategy/backtest.py 로 후보 버전 검증 (1Y 이상)
    │  승률·MDD·샤프 지수·수익 팩터가 기존 버전 대비 열화되지 않아야 함
    ▼
Discord #stock-system 에 개선안 요약 + 백테스트 결과 게시
    │  개발자가 /version 명령으로 검토
    ▼
승인 ──── 반려
  │         └── 폐기, reflections에 사유 기록
  ▼
strategy_versions 테이블에 새 버전 등록 (semver 증가)
core/trading/prompts/*.md 갱신 (L1 캐시 무효화 — 배포 전 확인 필수)
  ▼
SIMULATION 모드로 최소 1주 재검증 (기존 SIMULATION 절차 재사용, docs/SAFETY.md)
  ▼
문제 없으면 실전 반영, 문제 있으면 이전 strategy_version / prompt_version 으로 즉시 롤백
```

---

## 개선 후보의 출처

| 출처 | 내용 | 저장 위치 |
|------|------|-----------|
| Reflection (일일 자기평가) | 오늘 놓친 기회·잘못된 판단·Safety Gate 거부 타당성 | `reflections` 테이블 |
| 주간 성과 리포트 | 승률·MDD·샤프 지수 추세 | `logs/reports/` |
| 백테스트 재실행 | 새 시장 데이터로 기존 전략 재검증 | `core/strategy/backtest.py` |
| 개발자 수동 피드백 | Discord 명령으로 직접 지적한 오판 사례 | `decisions.actual_outcome` |

Claude 호출은 하루 1회(Reflection)로 제한된다. 개선 후보 추출 자체가 별도의 상시 호출을
발생시키지 않는다 (CLAUDE.md 절대 규칙 5 — 비용 절감 원칙 유지).

---

## 검증 없이 배포 금지

새 `prompt_version` / `strategy_version` 후보는 아래 순서를 모두 통과해야 실전에 반영된다.

| 단계 | 통과 기준 | 실패 시 |
|------|-----------|---------|
| 1. 백테스트 (1Y 이상) | 기존 버전 대비 승률·샤프 지수·MDD 열화 없음 | 후보 폐기 |
| 2. 개발자 승인 | Discord `#stock-system`에서 수동 확인 | 후보 폐기 |
| 3. SIMULATION 재검증 (최소 1주) | `docs/SAFETY.md` 시뮬레이션 전환 체크리스트 통과 | 이전 버전 유지 |
| 4. 실전 반영 | 7일 모니터링 이상 없음 | 즉시 롤백 |

---

## 버전 관리 및 롤백

```python
# strategy_versions 테이블 예시
{
  "strategy_version": "v1.3.0",
  "prompt_version": "system_kr_v4",
  "based_on": "v1.2.0",
  "change_summary": "RSI 반등 확인 조건에 거래량 가중치 추가",
  "backtest_result": {"win_rate": 0.68, "mdd": -0.041, "sharpe_ratio": 1.92},
  "approved_by": "discord:Ruthgyeul",
  "deployed_at": "2026-07-20T08:50:00+09:00"
}
```

롤백은 `strategy_versions`에서 이전 레코드를 찾아 `core/trading/prompts/*.md`와
전략 파라미터를 되돌리는 것만으로 완료된다 — 별도 마이그레이션이 필요 없도록
프롬프트·전략 파일은 항상 버전 이름이 파일명에 드러나야 한다 (`system_kr_v3`, `system_kr_v4` ...).

---

## 하드 금지 사항

- Safety Gate 조건(`core/safety/gate.py`)을 자기개선 루프가 직접 수정하지 않는다
- `INITIAL_SEED_KRW`, `CASH_BUFFER_RATIO`, `MAX_POSITION_RATIO` 등 자금·리스크 상수는 대상 외
- 백테스트를 거치지 않은 전략/프롬프트 변경은 실전은 물론 SIMULATION에도 반영하지 않는다
- 개발자 승인 없이 `strategy_versions`에 새 버전을 `deployed_at`으로 표시하지 않는다
- 자기개선 루프 자체가 별도의 상시 Claude 호출(에이전트 루프)을 만들지 않는다 —
  하루 1회 Reflection 호출 결과를 재사용한다 (CLAUDE.md — 에이전트 프레임워크 금지 원칙과 동일한 이유)

---

## 관련 문서

- `docs/BIN.md` — Reflection, 프롬프트·전략 버전 관리
- `docs/SAFETY.md` — SIMULATION 전환 체크리스트, 하드 금지 사항
- `docs/CODING_RULES.md` — 확장성 원칙 (새 전략은 `BaseStrategy` 상속)
