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

## 주간 분석·뉴스레터 실행

평소에는 운영 BO 서버 crontab 이 `run-weekly.sh` 로 정시에 실행한다. GitHub Actions 는 서버가 그 주 작업을 시작조차 못 했을 때만 일하는 안전망이다.

### 실행 시각 (KST)

| 시각 | 작업 | 실행 주체 |
|---|---|---|
| 월 07:00 | 공통 분석(`trend`). 끝나면 바로 사용자 분석(`user-analysis`) | 서버 |
| (공통 분석 직후) | 사용자 분석은 그날 일일 통계 20세트가 모일 때까지 최대 90분 기다린 뒤 시작 | 서버 |
| 월 09:30 | 뉴스레터 발송(`newsletter`) | 서버 |
| 월 12:10 | 분석 안전망 (`Weekly Analysis Batch`) | GitHub |
| 월 13:10 | 발송 안전망 (`Weekly Newsletter Batch`) | GitHub |

시간 제한(`timeout`): trend 10분, user-analysis 135분, newsletter 48분. 넘기면 강제 종료되고 Slack 에 "시간 제한 초과"가 간다.

### 서버 crontab

서버 시간대는 UTC 다. 사용자 분석은 공통 분석 결과 행이 있어야 하므로 반드시 한 줄로 잇는다. 서버가 꺼져 있어 놓친 시각은 다시 돌리지 않는다(그 주는 GitHub 안전망과 미실행 알림이 맡는다).

```cron
0 22 * * 0  <레포>/run-weekly.sh trend && <레포>/run-weekly.sh user-analysis
30 0 * * 1  <레포>/run-weekly.sh newsletter
```

### `~/weekly-batch` 구조

gunicorn 과 같은 사용자로 돈다. 파일은 본인만 읽을 수 있다(`umask 077`).

```text
~/weekly-batch/
  trend.lock  user-analysis.lock  newsletter.lock   # flock 잠금. 작업이 끝날 때까지 유지
  logs/<작업>-<YYYYMMDD>.log                          # 8주(56일) 지난 파일은 시작할 때 삭제
  metrics/weekly_batch_<작업>.prom                    # node_exporter textfile 폴더. 성공(건너뜀 포함) 때만 갱신
```

지표: `vd_weekly_batch_last_success_timestamp_seconds{job="<작업>"}`. 결과 파일(`weekly_analysis_result.txt`, `newsletter_batch_result.txt`)과 건너뜀 표시 파일(`<스크립트>.skipped`)은 레포 폴더에 생긴다.

### 서버 `.env.prod` 키

값은 적지 않는다. 코드에서 읽는 키만 나열한다.

| 용도 | 키 |
|---|---|
| 공통 | `SECRET_KEY`(필수), `DATABASE_ENGINE`, `DATABASE_NAME`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST` |
| 분석 | `OPENAI_API_KEY` |
| 발송 | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `DEFAULT_FROM_EMAIL`, `NEWSLETTER_UNSUBSCRIBE_SECRET` |
| 선택 | `SENTRY_DSN`, `SENTRY_TRACES_SAMPLE_RATE`, `SLACK_WEBHOOK_URL`(`run-weekly.sh` 가 읽음, 없으면 Slack 알림만 생략) |

`POSTGRES_PORT` 는 스크립트가 pooler 트랜잭션 모드(6543)로 고정하므로 `.env.prod` 값을 쓰지 않는다. 뉴스레터 서명 키가 없거나 32바이트보다 짧으면 발송은 계속하되 이메일 수신거부 링크로 보낸다.

### 수동 실행

서버에서는 항상 `run-weekly.sh` 로 돌린다. 파이썬 스크립트를 직접 부르면 잠금과 GitHub run 겹침 확인을 거치지 않는다.

```bash
cd <레포>
./run-weekly.sh trend           # 공통 분석
./run-weekly.sh user-analysis   # 사용자 분석 (이번 주 공통 분석 행 필요)
./run-weekly.sh newsletter      # 뉴스레터 발송
```

GitHub 에서 돌릴 때는 `gh workflow run "Weekly Analysis Batch"` 또는 `gh workflow run "Weekly Newsletter Batch"`. `workflow_dispatch` 도 판정 job(`guard`)을 거치므로, 서버가 이미 시작했거나 끝낸 주에는 본 작업 없이 조용히 건너뛴다.

실패한 GitHub run 은 다시 돌리지 않는다(`Re-run all jobs` 포함). `guard` 가 첫 시도가 남긴 DB 기록(이번 주 공통 분석 행, 발송 시작 표시)을 보고 본 작업 없이 조용히 끝날 수 있다. 실패한 주를 다시 돌릴 때는 서버에서 `./run-weekly.sh <작업>` 으로만 한다.

### 건너뜀과 중복 방지

| 규칙 | 동작 |
|---|---|
| `flock` | 같은 작업이 이미 돌고 있으면 "이미 실행 중, 건너뜀"을 로그에 남기고 종료 코드 0 |
| GitHub 진행 중 run | 같은 워크플로의 run 이 진행 중이면 "GitHub run 진행 중, 건너뜀"으로 종료 코드 0. 조회가 실패하면 그대로 진행 |
| 이번 주 처리 표시 | 공통 분석: 이번 주 `WeeklyTrend` 행이 있으면 건너뜀. 사용자 분석: `insight._batch.user_analysis_completed_at` 이 있으면 건너뜀(없으면 이번 주 `UserWeeklyTrend` 가 없는 대상만 처리). 발송: 이번 주 행이 발송 완료(`is_processed`)면 건너뜀(그 주 발송 기록이 없으면 메일 없이 종료 코드 1 로 실패해 Slack ❌. 복구: admin 에서 처리 완료를 해제한 뒤 `./run-weekly.sh newsletter`), 첫 메일 전에 `_batch.newsletter_started_at` 기록 |
| 이미 받은 이메일 제외 | 이번 주 뉴스레터를 이미 받은 이메일은 대상에서 빼고(청크마다 다시 적용), 남은 대상이 0명이면 발송 완료로 표시 |

할 일 없이 끝나면 `<스크립트>.skipped` 표시 파일이 생기고 Slack 은 보내지 않는다. 발송은 `user_analysis_completed_at` 이 없으면 메일 0통으로 실패한다. 사용자 분석은 대상의 절반 이상이 실패하면 완료 표시 없이 종료 코드 1 로 끝난다.

### 검수 보류 주

- admin 에서 이번 주 행을 "발송 보류"로 두면 09:30 서버 발송 실패 Slack, 10:30 Grafana 미실행 알림, 13:10 GitHub 안전망 실패 Slack 이 가는 것이 정상이다.
- "보류 해제"를 했으면 바로 서버에서 `./run-weekly.sh newsletter` 로 보낸다. 해제만 하고 수동 발송을 하지 않으면 13:10 GitHub 안전망이 그날 자동으로 보낼 수 있다.
- 아직 보내지 않을 거면 보류를 유지한다.

### GitHub 안전망이 도는 조건

예약 시각이면 run 은 반드시 만들어지지만, 먼저 `guard` job(체크아웃·secret 파일·DB 쓰기 없음, DB 는 읽기 전용)만 돌고 아래 순서로 판정한다.

| 순서 | 조건 | 결과 |
|---|---|---|
| 1 | 예약 이벤트인데 KST 요일이 월요일이 아님 | 건너뜀 |
| 2 | 같은 워크플로에서 먼저 만들어진 예약·수동 run 이 대기·진행 중 | 건너뜀 |
| 3 | 분석: 이번 주 `WeeklyTrend` 행이 있음 / 발송: 이번 주 행이 `is_processed` 이거나 `_batch.newsletter_started_at` 이 있음 | 건너뜀 |
| 4 | 그 밖(서버가 그 주 작업을 시작하지 못함) | 본 작업 실행, Slack 첫 줄에 "GitHub 안전망 실행" 표시 |

서버가 시작한 주는 서버가 끝까지 맡는다. 분석 판정은 공통 분석 행만 보고 사용자 분석 완료 여부는 보지 않는다. 그래서 행이 생긴 뒤 사용자 분석이 실패한 주는(GitHub 가 돌린 주도) GitHub 가 이어서 하지 않으니 서버에서 `./run-weekly.sh user-analysis` 로 잇는다. 서버 공통 분석이 실패해 행이 없는 주는 12:10 에 GitHub 가 다시 돈다. `guard` 가 실패하면 Slack 에 "안전망 판정 실패"가 간다.

### 배포 금지 시간

월요일 06:55~10:20 KST 에는 `run.sh` 로 배포하지 않는다. `run.sh` 는 시작할 때 `~/weekly-batch/*.lock` 을 잡아 보고, 하나라도 잡혀 있으면(주간 배치 실행 중) 배포를 멈추고 종료 코드 1 로 끝난다. 다만 검사 직후 cron 이 시작하는 경합은 막지 못하므로 위 시간대를 피한다.

### 장애 시 확인 순서

1. **Slack**: 작업별 메시지의 Status(success·failure·시간 제한 초과), Result, Log 경로를 본다. 메시지가 없으면 건너뜀이거나 Slack 웹훅이 없는 것이다.
2. **로그**: `~/weekly-batch/logs/<작업>-<날짜>.log` (`trend`·`user-analysis`·`newsletter`). 시작·종료 exit 코드와 건너뜀 사유가 KST 시각과 함께 남는다.
3. **결과·표시 파일**: 레포 폴더의 `weekly_analysis_result.txt`, `newsletter_batch_result.txt`, `*.skipped`. DB 에서는 이번 주 `insight_weeklytrend` 행과 `insight->'_batch'` 의 `user_analysis_started_at`·`user_analysis_completed_at`·`newsletter_started_at` 을 본다.
4. **재실행**: 서버에서 `./run-weekly.sh <작업>`. 이미 끝난 부분은 위 규칙으로 건너뛰고 남은 부분만 처리한다. 순서는 trend, user-analysis, newsletter.
5. **일일 통계 세트가 늦은 주 (발송 전에만)**: 사용자 분석 결과에 `경고: 일일 통계 세트 [...] 완료를 확인하지 못함` 이 있고 토큰 만료 수가 평소보다 많으면, 그 세트 사용자는 토큰 만료로 분류돼 이번 주 행이 없다(GitHub 조회만 실패했으면 토큰 만료 수는 평소와 같다). 세트가 끝난 뒤 이번 주 행에서 `_batch.user_analysis_completed_at` 만 지우고 `./run-weekly.sh user-analysis` 를 다시 돌린다. 이번 주 행이 없는 사용자만 다시 분석한다. 이 사용자 분석은 09:30 전에 **끝나야** 한다. 09:30 에 완료 표시가 없으면 예약 발송은 메일 없이 실패하므로, 그때는 분석이 끝난 뒤 바로 `./run-weekly.sh newsletter` 로 보낸다(보내지 않으면 13:10 GitHub 안전망이 보낼 수 있다).

   ```sql
   UPDATE insight_weeklytrend
   SET insight = insight #- '{_batch,user_analysis_completed_at}'
   WHERE week_end_date >= (date_trunc('week', now() AT TIME ZONE 'Asia/Seoul')::date - 1);
   ```

6. **Grafana 미실행 알림**: 월요일 10:30~12:00 KST 에 발송 지표(`job="newsletter"`)가 24시간 넘게 갱신되지 않았으면 울린다(규칙은 모니터링 서버에 있다). 서버는 살아 있는데 crontab 이 지워졌거나 스크립트가 시작 전에 죽은 경우다. 알림이 오면 1~4 순서로 확인한다.

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
