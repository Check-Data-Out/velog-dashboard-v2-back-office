import random
from datetime import datetime

from django.utils import timezone


def generate_random_group_id() -> int:
    return random.randint(1, 1000)


def get_local_now() -> datetime:
    """django timezone 을 기반으로 하는 실제 local의 now datetime"""
    utc_now = timezone.now()
    local_now: datetime = timezone.localtime(
        utc_now,
        timezone=timezone.get_current_timezone(),
    )
    return local_now


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
