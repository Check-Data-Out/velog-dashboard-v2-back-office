"""
[25.03.01] 리뉴얼 배치 (작성자: 정현우)
- 기본 scraping.main 에서 배치 비즈니스 로직 분리
- django 의존성 있는 배치라 setup_django 파일 및 세팅 필수 (ORM)
- timezone 워닝을 끄는 이유는 server 마다 타임존이 복잡한 상태라 batch 쪽에서 꺼둠
- (더욱이 배치가 실행되는 인스턴스 서버 타임존 역시 애매함)
- 실행은 아래와 같은 커멘드 활용
- python ./scraping/aggregate_batch.py
- python ./scraping/aggregate_batch.py --min-group 1 --max-group 1000
- poetry run python ./scraping/aggregate_batch.py --min-group 10 --max-group 20
"""

import argparse
import asyncio
import multiprocessing
import warnings

import setup_django  # noqa

from scraping.main import Scraper
from utils.utils import split_range


def run_scraper(group_range: range) -> None:
    """멀티프로세싱에서 실행될 동기 함수, 각 프로세스에서 비동기 루프 실행"""
    asyncio.run(Scraper(group_range).run())


def main() -> None:
    """커맨드라인 인자를 파싱하고 그룹 범위를 3분할하여 멀티프로세싱 처리"""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--min-group",
        type=int,
        default=1,
        help="Minimum group number",
    )
    parser.add_argument(
        "--max-group",
        type=int,
        default=1000,
        help="Maximum group number",
    )
    args = parser.parse_args()

    group_ranges = split_range(args.min_group, args.max_group, 3)
    processes = []
    for group_range in group_ranges:
        p = multiprocessing.Process(target=run_scraper, args=(group_range,))
        p.start()
        processes.append(p)

    for p in processes:
        p.join()


# Django에서 발생하는 RuntimeWarning 무시
warnings.filterwarnings(
    "ignore",
    message=r"DateTimeField .* received a naive datetime",
    category=RuntimeWarning,
)

if __name__ == "__main__":
    main()
