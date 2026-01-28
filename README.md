# velog-dashboard-v2-back-office

Velog-Dashboard v2의 데이터, 스크래핑, 백오피스용 레포지토리입니다.

## Requirements

- Python 3.13.0+
- Poetry 1.8.4+

## Installation

- `pyenv` 와 `poetry` 가 설치되었다고 가정하고 진행합니다.
- `poetry` 대신 `venv` 로 대체해서 사용가능합니다. (`requirements.txt` 활용)
- 참고로 `poetry` 기반으로 `poetry export -f requirements.txt --without-hashes -o requirements.txt` 통해 배포 require를 만들어야 합니다.

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
```

## Database Configuration

#### 1. [docker docs](https://docs.docker.com/get-started/)를 참고하여 Docker, Docker Compose 설치

#### 2. `docker compose up -d`로 실행

```bash
# 로컬: db + consumer 모두 실행 (override.yml 자동 로드)
docker compose up -d
```

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
# override.yml 무시 → consumer만 실행, 외부 DB 사용
docker compose -f docker-compose.yaml --env-file .env.prod up -d

# 로그 확인
docker compose -f docker-compose.yaml logs -f stats-refresh-consumer
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
