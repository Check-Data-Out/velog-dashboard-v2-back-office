# Stats Refresh Consumer

통계 새로고침 요청을 Redis 큐에서 받아서 처리하는 Consumer 프로세스입니다.

## 📋 개요

- **목적**: API로부터 받은 통계 새로고침 요청을 비동기적으로 처리
- **메시지 큐**: Redis List를 메시지 큐로 활용
- **처리 방식**: `ScraperTargetUser`를 사용하여 특정 사용자의 통계 갱신

## 🏗️ 아키텍처

```
┌──────────┐    POST       ┌─────────┐    LPUSH    ┌───────────────┐
│ Frontend │─────────────>│   API   │────────────>│ Redis Queue   │
└──────────┘  /refresh     └─────────┘             └───────────────┘
                                                           │ BRPOP
                                                           ▼
                                                   ┌──────────────┐
                                                   │   Consumer   │
                                                   │   Process    │
                                                   └──────────────┘
                                                           │
                                                           ▼
                                              ┌──────────────────────┐
                                              │ ScraperTargetUser    │
                                              │ Batch Process        │
                                              └──────────────────────┘
```

## 📁 디렉토리 구조

```
consumer/
├── __init__.py
├── setup_django.py          # Django 초기화
├── config.py                # 설정 (Redis, Consumer)
├── redis_client.py          # Redis 클라이언트
├── message_handler.py       # 메시지 처리 로직
├── stats_refresh_consumer.py # 메인 Consumer 프로세스
├── logger_config.py         # 로깅 설정
├── tests/                   # 테스트 코드
│   ├── conftest.py
│   ├── test_redis_client.py
│   ├── test_message_handler.py
│   └── test_stats_refresh_consumer.py
└── README.md
```

## 🚀 실행 방법

### 1. 로컬 실행

```bash
# Poetry를 사용하여 실행
poetry run python -m consumer.stats_refresh_consumer

# 또는 실행 스크립트 사용
./run_consumer.sh
```

### 2. Docker 실행

```bash
# Docker Compose로 실행
docker-compose up stats-refresh-consumer

# 백그라운드 실행
docker-compose up -d stats-refresh-consumer

# 로그 확인
docker-compose logs -f stats-refresh-consumer
```

## ⚙️ 환경 변수

`.env` 파일에 다음 환경 변수를 설정하세요:

```bash
# Redis 설정
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=notion-check-plz
REDIS_DB=0

# Consumer 설정
CONSUMER_LOG_LEVEL=INFO                    # DEBUG, INFO, WARNING, ERROR
CONSUMER_GRACEFUL_SHUTDOWN_TIMEOUT=30     # seconds

# Database 설정 (Django 필요)
DATABASE_ENGINE=timescale.db.backends.postgresql
DATABASE_NAME=postgres
POSTGRES_USER=vd2
POSTGRES_PASSWORD=vd2
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# AES 암호화 키
AES_KEY_0=...
AES_KEY_1=...
# ... (AES_KEY_9까지)

# Sentry (선택사항)
SENTRY_DSN=https://...
SENTRY_ENVIRONMENT=production
SENTRY_TRACES_SAMPLE_RATE=0.2
```

## 📊 Redis 큐 구조

### 메인 큐

- **`vd2:queue:stats-refresh`**: 새로고침 요청 대기열

### 처리 큐

- **`vd2:queue:stats-refresh:processing`**: 처리 중인 작업 추적
- **`vd2:queue:stats-refresh:failed`**: 실패한 작업 재처리용

### 메시지 포맷

```json
{
  "userId": 123,
  "requestedAt": "2025-12-12T10:30:00Z",
  "retryCount": 0
}
```

## 🔧 주요 기능

### 1. 메시지 처리

- **BRPOP**: Blocking right pop으로 메시지 대기 (타임아웃: 5초)
- **재시도 로직**: 최대 3회 재시도 (Exponential backoff: 2^n초)
- **에러 핸들링**: Sentry로 에러 리포팅

### 2. Graceful Shutdown

- **SIGTERM/SIGINT** 시그널 처리
- 현재 처리 중인 메시지 완료 대기 (최대 30초)
- Redis 연결 정리

### 3. 로깅

- **파일**: `logs/consumer.log` (Daily rotation, 30일 보관)
- **콘솔**: INFO 레벨
- **포맷**: 타임스탬프, 레벨, 함수명, 라인 번호 포함

### 4. 통계

실시간 처리 통계 추적:
- `processed`: 처리한 메시지 수
- `succeeded`: 성공한 메시지 수
- `failed`: 실패한 메시지 수
- `uptime`: Consumer 가동 시간

## 🧪 테스트

```bash
# 모든 테스트 실행
poetry run pytest consumer/tests/

# 특정 테스트 파일 실행
poetry run pytest consumer/tests/test_redis_client.py

# 커버리지와 함께 실행
poetry run pytest consumer/tests/ --cov=consumer --cov-report=html
```

## 📈 모니터링

### 로그 확인

```bash
# 실시간 로그
tail -f logs/consumer.log

# 특정 날짜 로그
cat logs/consumer.log.2025-12-12

# 에러만 필터링
grep "ERROR" logs/consumer.log
```

### 큐 상태 확인

```bash
# Redis CLI로 큐 사이즈 확인
redis-cli -h localhost -p 6379
> LLEN vd2:queue:stats-refresh
> LLEN vd2:queue:stats-refresh:processing
> LLEN vd2:queue:stats-refresh:failed
```

## ⚠️ 주의사항

1. **동시성**: 동일 사용자에 대한 중복 처리 방지는 API 레벨에서 처리
2. **Redis 연결**: Redis가 실행 중인지 확인 후 Consumer 시작
3. **Database**: Django ORM 사용으로 Database 연결 필수
4. **메모리**: 메시지 처리 중 메모리 사용량 모니터링 권장

## 🔍 트러블슈팅

### Redis 연결 실패

```bash
# Redis 상태 확인
redis-cli ping

# Redis 서비스 시작
docker-compose -f ../velog-dashboard-v2-cache/docker-compose.yaml up -d
```

### Consumer 중단

```bash
# 로그 확인
tail -100 logs/consumer.log

# 프로세스 확인
ps aux | grep consumer

# 강제 종료
pkill -f stats_refresh_consumer
```

### 메시지 처리 실패

- Failed 큐 확인: `LLEN vd2:queue:stats-refresh:failed`
- 실패한 메시지 재처리: Failed 큐의 메시지를 메인 큐로 이동

## 📚 참고 자료

- [Redis Lists](https://redis.io/docs/data-types/lists/)
- [Python Logging](https://docs.python.org/3/library/logging.html)
- [Django Signals](https://docs.djangoproject.com/en/5.0/topics/signals/)
