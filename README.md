# velog-dashboard-v2-back-office

Velog-Dashboard v2의 데이터, 스크래핑, 백오피스용 레포지토리입니다.

## Requirements

- Python 3.13.0+
- Poetry 1.8.4+

## Installation

- `pyenv` 와 `poetry` 가 설치되었다고 가정하고 진행합니다.
- `poetry` 대신 `venv` 로 대체해서 사용가능합니다. (`requirements.txt` 활용)
- 운영 웹은 `requirements.txt` 로 설치합니다. 이 파일은 `poetry.lock` 이 바뀌면 pre-commit 의 `poetry-export` 훅이 다시 만듭니다(`pre-commit install` 필요). CI 도 lock 과 일치하는지 검사합니다.

```bash
# 프로젝트 Clone 및 이동
git clone https://github.com/Check-Data-Out/velog-dashboard-v2-back-office.git
cd velog-dashboard-v2-back-office

# 전역적으로 3.13 python version 이 아니라면
pyenv local 3.13

# 가상환경 생성 및 패키지 설치
poetry shell
poetry install
```

## Environment Configuration

### 환경 파일 구조

```
.env.sample    # 템플릿 (git 추적)
.env           # 로컬용 (git 무시)
.env.prod      # 프로덕션용 (git 무시)
```

### DJANGO_SETTINGS_MODULE 자동 설정

환경 변수에서 직접 설정할 필요 없음. 진입점에서 자동 설정됨:

| 진입점 | Settings Module | 용도 |
|--------|-----------------|------|
| `manage.py` | `local` | 로컬 개발 (runserver) |
| `wsgi.py` (gunicorn) | `prod` | 프로덕션 웹 서버 |
| `docker-compose.yaml` | `consumer` | Consumer 프로세스 |

### 환경 파일 설정

```bash
# 1. 템플릿 복사
cp .env.sample .env

# 2. notion을 참조하여 실제 값 입력
# ⚠️ .env 파일이 없거나 SECRET_KEY가 없으면 실행 불가
# ⚠️ 로컬 이벤트가 운영 Sentry 프로젝트로 섞이지 않도록 로컬 `.env` 의 `SENTRY_DSN` 은 비워 둔다
```

## Database Configuration

#### 1. [docker docs](https://docs.docker.com/get-started/)를 참고하여 Docker, Docker Compose 설치

#### 2. `docker compose up -d`로 실행

```bash
# 로컬: db(postgres:17) + consumer 모두 실행 (override.yml 자동 로드)
docker compose up -d
```

- 기존 `.env` 의 `DATABASE_ENGINE` 이 `timescale.db.backends.postgresql` 이면 `django.db.backends.postgresql` 로 바꾼다 (postgres:17 에는 timescaledb 가 없어 `migrate` 가 실패한다).
- 로컬 DB 데이터는 `./postgres_data` 에 저장된다. 메이저 버전이 다른 데이터(예전 postgres:15 의 `./postgres_data`, TimescaleDB 컨테이너의 `./timescale_data*`)로는 postgres:17 이 시작되지 않으므로, **`docker compose up -d` 전에** 지우고(필요하면 먼저 백업) 기동 후 다시 `migrate` 한다.

## Pre-configue

- **_DB 세팅 이후, 실행 전 꼭 `superuser` 을 만들어야 admin 진입 가능_**

1. `docker` 를 띄우고 `python manage.py migrate` 실행, 아래와 같은 화면

```bash
Operations to perform:
  Apply all migrations: admin, auth, contenttypes, posts, sessions, users
Running migrations:
  Applying contenttypes.0001_initial... OK
  Applying auth.0001_initial... OK
  Applying admin.0001_initial... OK
  ... # 생략
```

2. `python manage.py createsuperuser` 실행 해서 따라가거나, 아래 명령어 복붙으로 실행

```bash
DJANGO_SUPERUSER_USERNAME=admin \
DJANGO_SUPERUSER_EMAIL=admin@example.com \
DJANGO_SUPERUSER_PASSWORD=admin \
python manage.py createsuperuser --noinput
```

- `Superuser created successfully.` 결과를 만나면 성공
- 그리고 아래 순서 F/U

## Run Test

### 1) unit testing

```bash
poetry run pytest -v  # 또는 pytest -v
# 또는 아주 상세 디버깅을 위해
poetry run pytest -v --full-trace --showlocals --tb=long --capture=no  # 또는 pytest 이후부터 쭉
```

- `conftest.py` 파일은 `pytest` 을 위한 자동 `fixture` 세팅 파일임
- 테스트 DB 는 로컬에서만 만든다. DB HOST 가 `localhost`/`127.0.0.1`/`db`/빈 값이 아니면 `conftest.py` 가 세션을 중단한다. 운영 접속정보로 `pytest`·`manage.py test`·`manage.py migrate` 를 실행하지 않는다
- `coverage` 는 아래와 같이 사용함

```bash
poetry run coverage run -m pytest
poetry run coverage report -m
poetry run coverage html
```

### 2) formatting & linting

```bash
# Formatting
poetry run ruff format

# Linting
poetry run ruff check --fix
```

### 3) register pre-commit

- need to be done `poetry config`

```bash
poetry show pre-commit  # check the result
poetry run pre-commit install  # the result will be >> pre-commit installed at .git/hooks/pre-commit

# pre-commit testing
poetry run pre-commit run --all-files
```

## Queue 운영 (Back-office)

백오피스 큐 운영 기능 가이드 — stats refresh 큐 모니터링, DLQ 관리, 컨슈머 헬스체크, 요청 추적, 배치 알림.

### Admin URL

| URL | 용도 |
|---|---|
| `/admin/queue/dashboard/` | 3개 큐(pending/processing/failed) 크기 대시보드 |
| `/admin/queue/failed/` | DLQ 조회 및 retry / purge |
| `/admin/ops_tracking/statsrefreshrequest/` | stats refresh 요청 추적 (누가·언제·성공/실패) |
| `/admin/posts/post/?stats_status=missing` | 오늘 통계 누락 포스트 필터 |

### Consumer Health

- Consumer 컨테이너 내부 `http://127.0.0.1:8081/healthz` (기본 포트, env `CONSUMER_HEALTHZ_PORT`)
- 응답: `{"status": "ok|stale", "redis": bool, "heartbeat_age_sec": float, ...}`
- Docker HEALTHCHECK 로 자동 체크되며, `interval=30s / timeout=5s / retries=3 / start-period=20s`
- **단일 consumer 인스턴스 전제** (Reclaimer daemon thread 가 포함). 다중 인스턴스 확장 시 분산 락 도입 필요.

### 핵심 환경 변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `REDIS_HOST/PORT/PASSWORD/DB` | localhost/6379 | Redis 연결 |
| `REDIS_MAX_FAILED_QUEUE_SIZE` | 10000 | DLQ 최대 크기 |
| `RECLAIM_VISIBILITY_TIMEOUT_SEC` | 600 | processing 메시지 stuck 판정 임계 |
| `RECLAIM_INTERVAL_SEC` | 60 | Reclaimer 루프 주기 |
| `RECLAIM_MAX_RECLAIMS` | 3 | reclaim 초과 시 DLQ |
| `CONSUMER_MAX_CONSECUTIVE_ERRORS` | 30 | 하드 종료 임계 (tenacity 재연결 포함) |
| `CONSUMER_HEALTHZ_PORT` | 8081 | /healthz 포트 (내부 bind) |
| `CONSUMER_HEALTHZ_STALE_THRESHOLD_SEC` | 60 | idle false-stale 방지 |
| `SLACK_OPS_WEBHOOK` | (미설정) | 운영 알림 웹훅 — 미설정 시 no-op |

### 장애 복구

- Consumer crash 시 processing 큐에 잔존한 메시지는 **재기동 직후 cold-start reclaim** 에서 pending 으로 자동 복원됨.
- `reclaimedCount > RECLAIM_MAX_RECLAIMS` 는 poison pill 로 간주하여 DLQ 로 이동.
- DLQ 수동 retry 는 `/admin/queue/failed/` 에서 버튼 클릭.

### 메시지 Envelope

외부 producer(velog-dashboard 웹) 가 보낸 메시지는 필요한 신규 필드(`requestId`, `enqueuedAt`, `reclaimedCount`, `requestedBy`, `processingStartedAt`) 가 누락되어 있어도 consumer 의 `ensure_envelope` 가 자동 보강한다. 외부 변경 불필요.

### Stats 데이터 정리 (cleanup_old_stats)

`PostDailyStatistics` 의 6개월 이전 데이터를 폐기. `drop_chunks` 를 먼저 시도(일반 테이블이거나 TimescaleDB 가 없으면 — 운영 — 건너뜀)한 뒤 남은 행을 ORM chunk DELETE 로 정리한다. 매일 KST 04:00 cron 자동 실행 (`.github/workflows/run-daily-stats-cleanup.yaml`). 초기 1회는 누적 데이터로 오래 걸리나 이후는 1일치만 정리되어 빠름.

운영 DB 는 Supabase 기반 PostgreSQL 17 (`posts_postdailystatistics` 는 일반 테이블). Session Mode(5432)·Transaction Mode(6543) 모두 동작한다 — `SET LOCAL` 은 `transaction.atomic` 안에서만 쓰여 트랜잭션 범위로 끝나고, Django 는 prepared statement 를 쓰지 않으며 서버 측 커서는 설정에서 꺼 두었다. Actions 배치(일일·주간·정리)는 모두 secret `POSTGRES_PORT` 하나로 포트를 정하므로, 이 값을 바꾸면 전부 함께 옮겨 간다. 운영 DB role 은 `run-daily-aggre-set*.yaml` 의 `POSTGRES_USER` 와 동일 (이미 매일 stats INSERT/UPDATE/DELETE 권한 보유).

같은 workflow 의 `db-invariants` job 이 매일 `manage.py check_db_invariants` 로 운영 DB 에 `timescaledb` 확장이나 `test_*` DB 가 없는지, 일별 통계 유니크 제약(`posts_pds_post_date_uniq`, 아래 절)이 있는지 검사하고, 위반 시 Slack 으로 알린다. Supabase 의 TimescaleDB(Apache 빌드)는 기본 job 이 라이선스 오류로 초당 1회 실패하며 로그를 무한히 쌓아 디스크를 키운다.

```bash
# 로컬 dry-run
poetry run python manage.py cleanup_old_stats --dry-run
# 운영 수동 실행 (workflow_dispatch)
gh workflow run "Daily Stats Cleanup" -f retention_months=6 -f dry_run=true
```

### 일별 통계 (post_id, date) 중복 정리

`posts` 0008 마이그레이션은 `posts_postdailystatistics` 에 `(post_id, date)` 유니크 제약 `posts_pds_post_date_uniq` 를 무중단으로 추가한다. `CREATE UNIQUE INDEX CONCURRENTLY` 로 인덱스를 만든 뒤 같은 이름으로 `ADD CONSTRAINT … UNIQUE USING INDEX` 승격한다. 세션의 `statement_timeout`·`lock_timeout`(PostgreSQL 17 이상은 `transaction_timeout` 도)을 직접 조정하므로 Session Mode(5432) 또는 Direct Connection 에서 실행한다.

같은 (post_id, date) 행이 이미 있으면 인덱스를 만들기 전에 중복 그룹 수를 알리며 실패한다. 아래 순서로 정리한 뒤 다시 `migrate` 한다. `--fake` 로 건너뛰면 제약 없이 적용 기록만 남으므로 쓰지 않는다. 같은 그룹의 행은 값이 같아서 그룹마다 `min(id)` 한 행만 남겨도 정보가 사라지지 않는다.

```sql
-- 1) 개수 확인 (extra = 지울 행 수)
SELECT count(*) AS pairs, sum(c - 1) AS extra
FROM (SELECT post_id, date, count(*) AS c FROM posts_postdailystatistics
      GROUP BY 1, 2 HAVING count(*) > 1) s;

-- 2) 지울 행 백업 (psql)
\copy (WITH d AS (SELECT post_id, date, min(id) AS keep_id FROM posts_postdailystatistics GROUP BY post_id, date HAVING count(*) > 1) SELECT s.* FROM posts_postdailystatistics s JOIN d ON s.post_id = d.post_id AND s.date = d.date AND s.id <> d.keep_id) TO 'pds_dup_rows.csv' CSV HEADER

-- 3) 정리. 두 곳의 0 을 1) 의 extra 로 바꾼다. 지운 행 수가 다르면 예외로 전부 롤백된다.
SET statement_timeout = '15min';
DO $$
DECLARE n bigint;
BEGIN
  WITH d AS (
    SELECT post_id, date, min(id) AS keep_id
    FROM posts_postdailystatistics
    GROUP BY post_id, date
    HAVING count(*) > 1
  )
  DELETE FROM posts_postdailystatistics s
  USING d
  WHERE s.post_id = d.post_id AND s.date = d.date AND s.id <> d.keep_id;
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> 0 THEN
    RAISE EXCEPTION 'deleted % rows, expected %', n, 0;
  END IF;
  RAISE NOTICE 'deleted % rows', n;
END $$;
```

인덱스 생성이 중간에 끊겨 INVALID 인덱스가 남아도 다시 `migrate` 하면 지우고 새로 만든다. 승격이 `lock_timeout`(3초)에 걸려 실패하면 유효한 인덱스가 남고, 다시 `migrate` 할 때 승격만 한다.

---

## Runserver

```bash
# Local 환경
python manage.py runserver

# Prod 환경으로 실행, 이 경우 `.env.prod` 필수
python manage.py runserver --settings=backoffice.settings.prod

# 이후 localhost:8000로 접속
# admin / admin 으로 로그인
```

## Stats Refresh Consumer

통계 새로고침 요청을 Redis 큐에서 받아 처리하는 Consumer 프로세스입니다.
상세 사용법은 ***[노션 링크를 참조](https://www.notion.so/nuung/25-12-28-back-office-2d76299fd66680ba8368e438f2b34478?source=copy_link)*** 해주세요. (멤버 전용)

### Docker 실행

#### 1. 이미지 빌드

mac/windows에서 빌드 시 이미지 크기가 커지므로 linux/amd64 플랫폼으로 직접 빌드 권장:

```bash
docker buildx build \
  --platform linux/amd64 \
  -f Dockerfile.consumer \
  -t stats-refresh-consumer:latest \
  --load \
  .
```

#### 2. 로컬 실행 (db + consumer)

```bash
# override.yml 자동 로드 → db + consumer 모두 실행
docker compose up -d

# 로그 확인
docker compose logs -f stats-refresh-consumer
```

#### 3. 프로덕션 실행 (consumer만)

```bash
# override.yml 무시 → consumer만 실행, env_file: .env.prod
docker compose -f docker-compose.yaml -f docker-compose.prod.yaml up -d

# 로그 확인
docker compose -f docker-compose.yaml -f docker-compose.prod.yaml logs -f stats-refresh-consumer
```

### Redis 큐 구조

**메인 큐**

- `vd2:queue:stats-refresh`: 새로고침 요청 대기열

**처리 큐**

- `vd2:queue:stats-refresh:processing`: 처리 중인 작업 추적
- `vd2:queue:stats-refresh:failed`: 실패한 작업 재처리용

**메시지 포맷**

```json
{
  "userId": 123,
  "requestedAt": "2025-12-12T10:30:00Z",
  "retryCount": 0
}
```
