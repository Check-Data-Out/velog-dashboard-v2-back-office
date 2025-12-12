#!/bin/bash

# Stats Refresh Consumer 실행 스크립트

set -e

# 색상 정의
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Stats Refresh Consumer${NC}"
echo -e "${GREEN}========================================${NC}"

# 환경 확인
if [ ! -f ".env" ]; then
    echo -e "${RED}Error: .env file not found${NC}"
    echo -e "${YELLOW}Please create .env file from .env.sample${NC}"
    exit 1
fi

# Poetry 확인
if ! command -v poetry &> /dev/null; then
    echo -e "${RED}Error: poetry is not installed${NC}"
    exit 1
fi

# Redis 연결 확인
echo -e "${YELLOW}Checking Redis connection...${NC}"
REDIS_HOST=${REDIS_HOST:-localhost}
REDIS_PORT=${REDIS_PORT:-6379}

if command -v redis-cli &> /dev/null; then
    redis-cli -h $REDIS_HOST -p $REDIS_PORT ping > /dev/null 2>&1
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Redis is running${NC}"
    else
        echo -e "${RED}✗ Redis is not running${NC}"
        echo -e "${YELLOW}Please start Redis first${NC}"
        exit 1
    fi
else
    echo -e "${YELLOW}Warning: redis-cli not found, skipping Redis check${NC}"
fi

# Consumer 실행
echo -e "${GREEN}Starting consumer...${NC}"
poetry run python -m consumer.stats_refresh_consumer
