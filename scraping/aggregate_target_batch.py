import asyncio
import multiprocessing
import warnings

import setup_django  # noqa
from django.db.models import Avg, Count

from scraping.main import Scraper
from users.models import User

# Django에서 발생하는 RuntimeWarning 무시
warnings.filterwarnings(
    "ignore",
    message=r"DateTimeField .* received a naive datetime",
    category=RuntimeWarning,
)


def run_scraper(group_range: range) -> None:
    """멀티프로세싱에서 실행될 동기 함수"""
    # 각 프로세스에서 비동기 루프 실행
    asyncio.run(Scraper(group_range).run())


def split_range(start: int, end: int, parts: int) -> list[range]:
    """주어진 범위를 지정된 수만큼 균등하게 분할"""
    width = end - start
    part_width = width // parts
    ranges = []

    for i in range(parts):
        part_start = start + (i * part_width)
        part_end = start + ((i + 1) * part_width) if i < parts - 1 else end
        ranges.append(range(part_start, part_end + 1))

    return ranges


def main() -> None:
    """커맨드라인 인자를 파싱하고 그룹 범위를 3분할하여 멀티프로세싱 처리"""

    # 1. 평균 게시글 수 구하기
    avg_posts_per_user = (
        User.objects.annotate(post_count=Count("posts")).aggregate(
            avg_posts_per_user=Avg("post_count")
        )
    )["avg_posts_per_user"]

    # 2. 평균보다 많은 게시글을 가진 사용자 필터링
    users_above_avg = (
        User.objects.annotate(post_count=Count("posts"))
        .filter(post_count__gt=avg_posts_per_user)
        .order_by("-id")
    )

    group_ranges = split_range(
        users_above_avg.first().group_id,
        users_above_avg.last().group_id,
        3,
    )

    processes = []
    for group_range in group_ranges:
        p = multiprocessing.Process(target=run_scraper, args=(group_range,))
        p.start()
        processes.append(p)

    for p in processes:
        p.join()


# 실행
if __name__ == "__main__":
    main()
