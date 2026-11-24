import json
import logging
import random
import re
import resource
from dataclasses import fields, is_dataclass
from datetime import date, datetime, timedelta
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


def get_this_week_monday(now: datetime | None = None) -> date:
    """now(기본 지금 KST)가 속한 주의 월요일 날짜. 월요일이면 그날"""
    today = (now or get_local_now()).date()
    return today - timedelta(days=today.weekday())


def get_local_now_date() -> datetime:
    """django timezone 을 기반으로 하는 실제 local의 now date"""
    local_now = get_local_now()
    return local_now.replace(hour=0, minute=0, second=0, microsecond=0)


def to_local_date(dt: datetime) -> datetime:
    """datetime 을 django timezone 을 따르는 date 로 cating 하는 함수"""
    local_dt = timezone.localtime(dt, timezone=timezone.get_current_timezone())
    result: datetime = local_dt.replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return result


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
    """start~end(양끝 포함)를 겹치지 않는 최대 parts 개 구간으로 분할

    end - start 가 parts 보다 작으면 앞쪽 구간이 빈다. 빈 구간을 받은
    프로세스는 Scraper.run 의 min()/max() 에서 죽으므로 빼고 돌려주며,
    이때는 start~end 전체 구간 1개만 나온다(예: 1~3 을 3분할).
    start 가 end 보다 크면 ValueError.
    """
    if start > end:
        raise ValueError(f"start({start}) 가 end({end}) 보다 큽니다.")

    width = end - start
    part_width = width // parts
    ranges = []

    for i in range(parts):
        part_start = start + (i * part_width)
        if i < parts - 1:
            # 다음 파트의 시작값은 제외한다. 포함하면 같은 그룹을 두
            # 프로세스가 처리해 (post, date) 중복 행이 생긴다.
            ranges.append(range(part_start, start + ((i + 1) * part_width)))
        else:
            ranges.append(range(part_start, end + 1))

    return [r for r in ranges if r]


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


def record_peak_memory(logger: logging.Logger, result_file: str) -> None:
    """이 프로세스의 최대 메모리를 로그 한 줄과 결과 파일 한 줄로 남긴다.

    Linux 의 ru_maxrss 단위는 KiB 라서 1024 로 나눠 MB 로 적는다.

    Args:
        logger: 로그를 남길 로거
        result_file: 줄을 덧붙일 결과 파일 경로
    """
    peak_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024
    logger.info("Peak memory: %d MB", peak_mb)
    try:
        with open(result_file, "a") as f:
            # 위 결과 줄은 실제 줄바꿈 없이 끝날 수 있으므로 새 줄에서 시작한다
            f.write(f"\n최대 메모리: {peak_mb} MB\n")
    except Exception as e:
        logger.error("Failed to save peak memory to %s: %s", result_file, e)
