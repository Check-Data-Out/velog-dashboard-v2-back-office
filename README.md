# velog-dashboard-v2-back-office

Velog-Dashboard v2의 데이터, 스크래핑, 백오피스용 레포지토리입니다.

## Requirements

- Python 3.13.0
- Poetry 1.8.4

## Installation

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

## Database Configuration
#### 1. [dockerdocs](https://docs.docker.com/get-started/)를 참고하여 Docker, Docker Compose 설치
#### 2. .env.sample의 형식으로 환경 변수 설정
#### 3. ```docker-compose up -d```로 실행 (또는 공백없이 `docker compose up -d`)

## Pre-configue

- ***DB 세팅 이후, 실행 전 꼭 `superuser` 을 만들어야 admin 진입 가능***

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
poetry run pytest
```

### 2) formatting & linting

```bash
# Formatting
ruff format

# Linting
ruff check --fix
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

# Prod 환경으로 실행
python manage.py runserver --settings=backoffice.settings.prod

# 이후 localhost:8000로 접속
# admin / admin 으로 로그인
```
