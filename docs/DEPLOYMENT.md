# DEPLOYMENT.md — 라즈베리파이 배포

> `docs/ARCHITECTURE.md`가 보여주는 systemd 유닛 파일 *내용*을 실제 설치·업데이트·
> 롤백·백업 연동 절차로 풀어낸 런북이다. 최초 배포와 이후 재배포 모두 이 문서를 따른다.

---

## 사전 준비

Ubuntu 24.04 LTS · Python 3.11+ · Node.js LTS · PostgreSQL · Redis
(하드웨어는 `CLAUDE.md` 하드웨어 섹션, 의존성 버전은 `README.md`/`docs/CODING_RULES.md`
참고 — 여기서 반복하지 않는다). 추가로 OS 패키지가 필요하다.

```bash
sudo apt update
sudo apt install -y git postgresql redis-server build-essential
```

---

## 최초 설치

1. **클론**
   ```bash
   git clone <repo-url> /home/ruthgyeul/TossInvestAI
   cd /home/ruthgyeul/TossInvestAI
   ```

2. **환경변수**
   ```bash
   cp .env.example .env
   # .env 값 채우기 (토스 API 키, Claude/Gemini/DeepSeek 키, DB·Redis URL, 내부 API 토큰 등)
   chmod 600 .env
   ```
   `.env`는 절대 git에 커밋하지 않는다 (CLAUDE.md 절대 규칙 2).

3. **PostgreSQL** — `.env`의 `DATABASE_URL=postgresql+asyncpg://bin:changeme@localhost:5432/bin_trading`에 맞춰 role/db 생성
   ```bash
   sudo -u postgres psql -c "CREATE USER bin WITH PASSWORD '<changeme>';"
   sudo -u postgres psql -c "CREATE DATABASE bin_trading OWNER bin;"
   ```

4. **Redis** — 기본 설치로 `REDIS_URL=redis://localhost:6379/0`과 바로 맞는다. 추가 설정 불필요.

5. **Python (venv 사용)**
   ```bash
   python3 -m venv /home/ruthgyeul/TossInvestAI/venv
   source /home/ruthgyeul/TossInvestAI/venv/bin/activate
   pip install -r requirements.txt
   ```

6. **DB 스키마 부트스트랩** — ⚠️ **TODO**: 아직 Alembic 등 마이그레이션 도구가 없다.
   `core/db/models.py`의 `Base.metadata`로 최초 1회만 테이블을 생성한다.
   ```bash
   python -c "
   import asyncio
   from sqlalchemy.ext.asyncio import create_async_engine
   from core.db.models import Base
   from core.config import settings

   async def main():
       engine = create_async_engine(settings.DATABASE_URL)
       async with engine.begin() as conn:
           await conn.run_sync(Base.metadata.create_all)

   asyncio.run(main())
   "
   ```
   스키마가 안정화되면(Phase 2 이후, docs/CODING_RULES.md 개발 순서) Alembic 도입을 검토한다 —
   지금은 스키마 변경 시 수동 `ALTER TABLE`이 필요하다는 뜻이다.

7. **discord-bot**
   ```bash
   cd discord-bot
   npm install
   npm run build
   cd ..
   ```

---

## systemd 유닛 설치

전체 유닛 파일 내용은 `deploy/systemd/bin-core.service`, `deploy/systemd/bin-discord.service`
참고 (여기서 다시 옮겨 적지 않는다).

```bash
sudo cp deploy/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now bin-core.service bin-discord.service

# 확인
systemctl status bin-core bin-discord
journalctl -u bin-core -f
```

> ⚠️ **알려진 격차**: `deploy/systemd/bin-core.service`의
> `ExecStart=.../venv/bin/python3 -m agent.loop`는 아직 존재하지 않는 `agent.loop`
> 모듈을 가리킨다 — `docs/ARCHITECTURE.md`의 원본 예시를 그대로 유지했다.
> Phase 4(트레이딩 루프 구현, docs/CODING_RULES.md 개발 순서)에서 실제 진입점이
> 만들어지면 이 값을 갱신해야 한다. **TODO로 남겨 둔다.**
>
> 또한 `deploy/systemd/`의 경로(`/home/ruthgyeul/TossInvestAI`, venv 사용)는
> `docs/ARCHITECTURE.md` 예시(`/home/pi/trading-bot`, venv 미사용)와 다르다 —
> **`deploy/systemd/`의 실제 파일을 최신 기준으로 삼는다.**

---

## 업데이트 / 재배포 절차

```bash
git pull
source venv/bin/activate && pip install -r requirements.txt
cd discord-bot && npm install && npm run build && cd ..
sudo systemctl restart bin-core bin-discord
```

> ⚠️ **장중 재시작 경고**: `core/trading/loop.py`가 시장별로 15분 주기 APScheduler
> 루프를 돌린다. 장중 재시작은 진행 중인 주문 제출을 방해할 위험이 있다.
>
> - 가능하면 장 마감 시간(KR 15:35 이후~08:50 이전, US 마감 이후, docs/REPORT.md
>   리포트 스케줄 참고)에 재시작한다.
> - 불가피하게 장중 재시작이 필요하면: `/stop` → 미체결 정리 대기 → 재시작 →
>   `/resume` 순서를 따른다 (docs/SAFETY.md 긴급 정지 절차와 동일).

---

## 백업/복구 연동

`core/scheduler/tasks.py`의 `register_all_jobs()`가 일/주/월 백업(docs/LOGGING.md
스케줄: 매일 03:00 / 매주 일요일 / 매월 1일)을 `bin-core.service` 내부 APScheduler
잡으로 이미 등록한다 — **별도 systemd timer나 cron이 필요 없다.**

> ⚠️ **TODO**: `bin-core`가 백업 예정 시각에 다운돼 있으면 캐치업 로직이 없어
> 조용히 누락될 수 있다. `core/db/backup.py`의 `run_daily_backup()` 등이 현재
> 빈 스텁이라 실패 알림도 아직 구현 전이다 — 운영자가 매일 아침 `backups/daily/`를
> 눈으로 확인하는 걸 임시 대책으로 권장한다.

월간 백업은 무제한 보관되므로, 256GB SSD에서 디스크 사용량을 주기적으로 확인한다
(`core/monitoring/health.py`의 `DISK_THRESHOLD_PCT=90.0` 초과 시 `#stock-error` 알림).

**복구 절차** (⚠️ TODO: 아직 CLI 진입점 없음, 임시 수동 호출):
```bash
sudo systemctl stop bin-core bin-discord
source venv/bin/activate
python -c "
import asyncio
from pathlib import Path
from core.db.backup import restore
asyncio.run(restore(Path('backups/daily/<파일명>')))
"
sudo systemctl start bin-core bin-discord
```

---

## 헬스체크 연동

`core/monitoring/health.py`가 `bin-core.service` 안에서 5분마다 자동 실행된다
(CPU>85%, 메모리>80%, 디스크>90%, 온도>75°C, 토스 API 무응답>30초 —
docs/LOGGING.md 임계값). 별도 설치가 필요 없다. `/health` 명령으로 수시 확인도
가능하다.

---

## 롤백 절차

**코드 롤백**
```bash
git log --oneline
git revert <bad-commit>   # 또는 이전 태그로 checkout
cd discord-bot && npm run build && cd ..
sudo systemctl restart bin-core bin-discord
```
배포마다 git 태그(`v0.1.0` 등)를 남기는 걸 새 관례로 권장한다 — 현재 저장소에는
없다 (TODO).

**전략/프롬프트 롤백**은 별도 절차다 — `docs/SELF_IMPROVEMENT.md`의
`strategy_versions` 테이블 롤백 절차를 그대로 따른다 (여기서 중복 설명하지 않는다).

**DB 롤백**: 두 서비스 정지 → 위 "백업/복구 연동"의 복구 절차 실행.
**LIVE(`trades`)와 SIMULATION(`simulation_trades`) 데이터는 롤백 중에도 절대
혼용하지 않는다** (docs/SAFETY.md, docs/LOGGING.md 하드 규칙).
