from insight.models import WeeklyTrendInsight
from utils.utils import from_dict


def test_legacy_empty_insight_json_restores():
    """필터 메타 필드가 없던 과거 빈 insight JSON 이 default 로 복원된다."""
    restored = from_dict(WeeklyTrendInsight, {})

    assert restored.trending_summary == []
    assert restored.trend_analysis is None


def test_legacy_populated_insight_json_restores():
    """과거 형태의 insight JSON 이 신규 필드 없이도 정상 복원된다.

    신규 dataclass 필드는 반드시 default 를 가져야 한다는 불변식을 잠근다.
    """
    legacy = {
        "trending_summary": [
            {
                "title": "옛 트렌딩 글",
                "summary": "요약",
                "key_points": ["a", "b"],
                "username": "old_user",
                "thumbnail": "https://velog.io/old.jpg",
                "slug": "old-post",
            }
        ],
        "trend_analysis": {
            "hot_keywords": ["python"],
            "title_trends": "",
            "content_trends": "",
            "insights": "",
        },
    }

    restored = from_dict(WeeklyTrendInsight, legacy)

    # list[TrendingItem] 은 dataclass 로 복원된다
    assert restored.trending_summary[0].title == "옛 트렌딩 글"
    # Optional dataclass(trend_analysis) 는 기존 동작상 dict 로 유지된다
    assert restored.trend_analysis["hot_keywords"] == ["python"]
