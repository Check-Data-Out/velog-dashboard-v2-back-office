from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from utils.utils import get_this_week_monday

KST = ZoneInfo("Asia/Seoul")


@pytest.mark.parametrize(
    "now, expected",
    [
        (datetime(2026, 11, 23, 0, 0, tzinfo=KST), date(2026, 11, 23)),
        (datetime(2026, 11, 24, 7, 0, tzinfo=KST), date(2026, 11, 23)),
        (datetime(2026, 11, 29, 23, 59, tzinfo=KST), date(2026, 11, 23)),
    ],
    ids=["월요일", "화요일", "일요일"],
)
def test_get_this_week_monday(now, expected):
    """어느 요일에 불러도 그 주의 월요일을 돌려준다(월요일이면 그날)"""
    assert get_this_week_monday(now) == expected
