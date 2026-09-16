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
