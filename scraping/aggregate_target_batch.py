import asyncio
import multiprocessing
import warnings

import setup_django  # noqa
from django.db.models import Avg, Count

from scraping.main import ScraperTargetUser
from users.models import User
from utils.utils import split_list

# Django에서 발생하는 RuntimeWarning 무시
warnings.filterwarnings(
    "ignore",
    message=r"DateTimeField .* received a naive datetime",
    category=RuntimeWarning,
)


def run_scraper(user_pk_list: list[int]) -> None:
    """멀티프로세싱에서 실행될 동기 함수, 각 프로세스에서 비동기 루프 실행"""
    asyncio.run(ScraperTargetUser(user_pk_list).run())


def main() -> None:
    """커맨드라인 인자를 파싱하고 그룹 범위를 3분할하여 멀티프로세싱 처리"""

    # 1. 모든 사용자에 대해 게시글 수를 계산하고 평균 게시글 수 구하기
    avg_posts_per_user = (
        User.objects.annotate(post_count=Count("posts")).aggregate(
            avg_posts=Avg("post_count")
        )
    )["avg_posts"]

    # 2. 평균보다 많은 게시글을 가진 사용자들 필터링 (정렬은 최신순)
    users_above_avg = (
        User.objects.annotate(post_count=Count("posts"))
        .filter(post_count__gt=avg_posts_per_user)
        .order_by("-id")
    )

    # 3. 필터링한 사용자들의 pk를 리스트로 추출
    user_pk_list = list(users_above_avg.values_list("pk", flat=True))

    processes = []
    for user_pk_list in split_list(user_pk_list, 2):
        p = multiprocessing.Process(target=run_scraper, args=(user_pk_list,))
        p.start()
        processes.append(p)

    for p in processes:
        p.join()


# 실행
if __name__ == "__main__":
    main()
