import pytest

from utils.utils import split_range


class TestSplitRange:
    @pytest.mark.parametrize(
        "start, end, parts",
        [(1, 50, 2), (101, 150, 2), (1, 1000, 2), (1, 10, 3)],
        ids=["set1", "set3", "전체", "3분할"],
    )
    def test_parts_do_not_overlap(self, start, end, parts):
        """분할된 구간이 서로 겹치지 않는지.

        겹치면 같은 그룹을 두 프로세스가 처리해 (post, date) 중복
        행이 생긴다.
        """
        ranges = split_range(start, end, parts)

        seen: set[int] = set()
        for r in ranges:
            assert not (seen & set(r))
            seen |= set(r)

    @pytest.mark.parametrize(
        "start, end, parts",
        [(1, 50, 2), (101, 150, 2), (1, 1000, 2), (1, 10, 3)],
        ids=["set1", "set3", "전체", "3분할"],
    )
    def test_parts_cover_whole_range(self, start, end, parts):
        """분할 결과의 합집합이 원래 범위 전체와 같은지"""
        ranges = split_range(start, end, parts)

        covered: set[int] = set()
        for r in ranges:
            covered |= set(r)
        assert covered == set(range(start, end + 1))

    @pytest.mark.parametrize(
        "start, end, expected",
        [(5, 5, [range(5, 6)]), (1, 2, [range(1, 3)])],
        ids=["그룹 1개", "그룹 2개"],
    )
    def test_skips_empty_parts_when_groups_fewer_than_parts(
        self, start, end, expected
    ):
        """그룹 수가 분할 수보다 적어도 빈 구간을 만들지 않는지.

        빈 구간을 받은 프로세스는 Scraper.run 의 min()/max() 에서
        ValueError 로 죽고, 배치 전체가 실패로 끝난다.
        """
        assert split_range(start, end, 2) == expected

    def test_raises_when_start_is_greater_than_end(self):
        """시작이 끝보다 크면 예외를 내는지.

        빈 목록을 돌려주면 배치가 프로세스 없이 성공(exit 0)으로 끝나
        잘못된 입력이 드러나지 않는다.
        """
        with pytest.raises(ValueError):
            split_range(10, 5, 2)
