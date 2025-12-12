import json
import random
import re
from dataclasses import fields, is_dataclass
from datetime import datetime, timedelta
from typing import Any, Type, TypeVar, get_args, get_origin, no_type_check

from django.utils import timezone

T = TypeVar("T")


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


def get_local_date() -> datetime:
    """django timezone 을 기반으로 하는 실제 local의 now date"""
    local_now = get_local_now()
    return local_now.replace(hour=0, minute=0, second=0, microsecond=0)


def parse_json(
    data: Any, default: dict[Any, Any] | None = None
) -> dict[Any, Any]:
    """데이터를 JSON 형식으로 안전하게 파싱"""
    if default is None:
        default = {}
    if isinstance(data, str):
        try:
            result: dict[Any, Any] = json.loads(data)
            return result
        except json.JSONDecodeError:
            return default
    if isinstance(data, dict):
        return data
    return default


def strip_html_tags(html: str) -> str:
    """HTML 태그를 제거한 문자열 반환"""
    return re.sub(r"<[^>]+>", "", html)


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


def split_list(lst: list[int], n_splits: int) -> list[list[int]]:
    """리스트를 n_splits개의 대략 동일한 크기의 서브 리스트로 나눕니다."""
    k, m = divmod(len(lst), n_splits)
    return [
        lst[i * k + min(i, m) : (i + 1) * k + min(i + 1, m)]
        for i in range(n_splits)
    ]


@no_type_check
def to_dict(obj: Any) -> Any:
    """재귀적으로 dataclass를 dict로 변환"""
    if is_dataclass(obj):
        return {f.name: to_dict(getattr(obj, f.name)) for f in fields(obj)}
    elif isinstance(obj, (list, tuple)):
        return [to_dict(v) for v in obj]
    elif isinstance(obj, dict):
        return {k: to_dict(v) for k, v in obj.items()}
    else:
        return obj


@no_type_check
def from_dict(cls: Type[T], data: dict[str, Any]) -> T:
    """dict에서 dataclass로 복원"""
    if not is_dataclass(cls):
        return data

    kwargs = {}
    for f in fields(cls):
        if f.name not in data:
            continue

        value = data[f.name]
        field_type = f.type

        # dataclass 타입 체크
        if is_dataclass(field_type):
            kwargs[f.name] = from_dict(field_type, value)
        # List[dataclass] 처리
        elif (
            get_origin(field_type) in (list, tuple)
            and len(get_args(field_type)) > 0
            and is_dataclass(get_args(field_type)[0])
        ):
            item_type = get_args(field_type)[0]
            kwargs[f.name] = [from_dict(item_type, item) for item in value]
        else:
            kwargs[f.name] = value

    return cls(**kwargs)


def get_previous_week_range(
    today: datetime | None = None,
) -> tuple[datetime, datetime]:
    """지금 시간대를 유지하면서 7일 전과 오늘 00:00 까지 날짜 범위 계산"""
    today = today or get_local_now()

    # 7일 전 (week_start) - local timezone 유지
    seven_days_ago = today - timedelta(days=7)
    week_start = timezone.make_aware(
        datetime.combine(seven_days_ago.date(), datetime.min.time()),
        timezone=today.tzinfo,
    )

    # 오늘 00:00:00 (week_end)
    week_end = timezone.make_aware(
        datetime.combine(today.date(), datetime.min.time()),
        timezone=today.tzinfo,
    )

    return week_start, week_end
