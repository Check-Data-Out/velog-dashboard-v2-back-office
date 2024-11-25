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

# 가상환경 생성 및 패키지 설치
poetry shell
poetry install
```

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
```
