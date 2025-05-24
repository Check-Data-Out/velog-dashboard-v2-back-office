import json
from dataclasses import dataclass
from typing import Type, TypeVar

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
    def to_dict(self) -> dict:
        return to_dict(self)

    def to_json_dict(self) -> dict:
        """Django Model의 JSON 필드 저장용"""
        return json.loads(json.dumps(self.to_dict()))

    @classmethod
    def from_dict(cls: Type[T], data: dict) -> T:
        return from_dict(cls, data)
