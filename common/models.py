import json
from dataclasses import dataclass
from typing import Any, Type, TypeVar, no_type_check

from django.db import models

from utils.utils import from_dict, to_dict


class TimeStampedModel(models.Model):  # type: ignore
    """
    생성일시, 수정일시 필드 베이스 모델
    """

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="생성 일시",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="수정 일시",
    )

    class Meta:
        abstract = True


T = TypeVar("T")


# dataclass 베이스 mixin
@dataclass
class SerializableMixin:
    @no_type_check
    def to_dict(self) -> dict[str, Any]:
        return to_dict(self)

    @no_type_check
    def to_json_dict(self) -> dict[str, Any]:
        """Django Model의 JSON 필드 저장용"""
        return json.loads(json.dumps(self.to_dict()))

    @classmethod
    @no_type_check
    def from_dict(cls: Type[T], data: dict[str, Any]) -> T:
        return from_dict(cls, data)
