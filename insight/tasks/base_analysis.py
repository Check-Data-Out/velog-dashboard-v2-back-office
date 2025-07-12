import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Generic, TypeVar

import aiohttp

from scraping.velog.client import VelogClient
from utils.utils import get_previous_week_range

T = TypeVar("T")  # 분석 결과 타입


@dataclass
class AnalysisContext:
    """분석 컨텍스트 정보"""

    week_start: datetime
    week_end: datetime
    velog_client: VelogClient


@dataclass
class AnalysisResult(Generic[T]):
    """분석 결과 래퍼"""

    success: bool
    data: T | None = None
    error: Exception | None = None
    metadata: dict[str, Any] | None = None


class BaseBatchAnalyzer(ABC, Generic[T]):
    """배치 분석 작업의 기본 추상 클래스"""

    def __init__(self):
        self.logger = logging.getLogger("newsletter")

    async def run(self) -> AnalysisResult[list[T]]:
        """메인 실행 메서드"""
        self.logger.info("Starting %s", self.__class__.__name__)

        try:
            # 1. 컨텍스트 초기화
            context = await self._initialize_context()

            # 2. 데이터 수집
            raw_data = await self._fetch_data(context)
            if not raw_data:
                self.logger.info("No data to process")
                return AnalysisResult(
                    success=True, data=[], metadata={"reason": "no_data"}
                )

            # 3. 분석 실행
            analysis_results = await self._analyze_data(raw_data, context)

            # 4. 결과 저장
            await self._save_results(analysis_results, context)

            self.logger.info(
                "Completed %s successfully", self.__class__.__name__
            )
            return AnalysisResult(
                success=True,
                data=analysis_results,
                metadata={"processed_count": len(analysis_results)},
            )

        except Exception as e:
            self.logger.exception(
                "Failed to run %s: %s", self.__class__.__name__, e
            )
            return AnalysisResult(success=False, error=e)

    async def _initialize_context(self) -> AnalysisContext:
        """분석 컨텍스트 초기화"""
        week_start, week_end = get_previous_week_range()

        session = aiohttp.ClientSession()
        velog_client = VelogClient.get_client(
            session=session,
            access_token="dummy_access_token",
            refresh_token="dummy_refresh_token",
        )

        return AnalysisContext(
            week_start=week_start,
            week_end=week_end,
            velog_client=velog_client,
        )

    @abstractmethod
    async def _fetch_data(self, context: AnalysisContext) -> list[Any]:
        """데이터 수집 (구현 필요)"""
        pass

    @abstractmethod
    async def _analyze_data(
        self, raw_data: list[Any], context: AnalysisContext
    ) -> list[T]:
        """데이터 분석 (구현 필요)"""
        pass

    @abstractmethod
    async def _save_results(
        self, results: list[T], context: AnalysisContext
    ) -> None:
        """결과 저장 (구현 필요)"""
        pass
