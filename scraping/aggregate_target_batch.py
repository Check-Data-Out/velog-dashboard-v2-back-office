import asyncio
import multiprocessing
import warnings

import setup_django  # noqa

from scraping.main import ScraperTargetUser

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

    # # 1. 평균 게시글 수 구하기
    # avg_posts_per_user = (
    #     User.objects.annotate(post_count=Count("posts")).aggregate(
    #         avg_posts_per_user=Avg("post_count")
    #     )
    # )["avg_posts_per_user"]

    # # 2. 평균보다 많은 게시글을 가진 사용자 필터링
    # users_above_avg = (
    #     User.objects.annotate(post_count=Count("posts"))
    #     .filter(post_count__gt=avg_posts_per_user)
    #     .order_by("-id")
    # )

    # 3. 해당 user 들 pk list 형태로 파싱, 2 덩어리로 찢음
    list_of_user_pk_list: list[list[int]] = [[1, 2, 3], [4, 5, 6]]

    processes = []
    for user_pk_list in list_of_user_pk_list:
        p = multiprocessing.Process(target=run_scraper, args=(user_pk_list,))
        p.start()
        processes.append(p)

    for p in processes:
        p.join()


# 실행
if __name__ == "__main__":
    main()
