import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"


def test_daily_set_ranges_partition_all_groups():
    """세트 배치들이 그룹 1~1000 을 겹침·빈틈 없이 나눠 맡는지.

    상한 1000 은 가입 때 그룹을 고르는 범위다(API 의 generateRandomGroupId, 모델
    기본값 generate_random_group_id). 두 세트가 같은 그룹을 맡으면 같은 게시글을
    거의 동시에 처리해 일별 통계 행이 중복된다. 스케줄 실행은 cron 대체값(`|| 'N'`)을 쓰므로 그 값으로 구간을
    펼치고, 수동 실행 기본값(`default: 'N'`)과도 같은지 본다.
    """
    groups = []
    for path in sorted(WORKFLOWS_DIR.glob("run-daily-aggre-set*.yaml")):
        text = path.read_text(encoding="utf-8")
        defaults = re.findall(r"default: '(\d+)'", text)
        fallbacks = re.findall(r"\|\| '(\d+)'", text)
        assert defaults == fallbacks, path.name
        assert len(fallbacks) == 2, path.name

        low, high = (int(value) for value in fallbacks)
        groups.extend(range(low, high + 1))

    assert sorted(groups) == list(range(1, 1001))
