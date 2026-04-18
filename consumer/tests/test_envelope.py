"""consumer/envelope.py 테스트."""

from consumer.envelope import build_envelope, ensure_envelope


class TestBuildEnvelope:
    def test_sets_request_id_user_id_and_timestamps(self):
        env = build_envelope(user_id=123, requested_by=42)
        assert env["userId"] == 123
        assert env["requestedBy"] == 42
        assert env["retryCount"] == 0
        assert env["reclaimedCount"] == 0
        assert env["requestId"]  # non-empty uuid
        assert env["enqueuedAt"]
        assert env["requestedAt"] == env["enqueuedAt"]

    def test_accepts_custom_request_id(self):
        env = build_envelope(user_id=1, request_id="rid-xyz")
        assert env["requestId"] == "rid-xyz"


class TestEnsureEnvelope:
    def test_adds_missing_fields(self):
        raw = {"userId": 1, "requestedAt": "2026-04-18T00:00:00+09:00"}
        result = ensure_envelope(raw)
        assert result["userId"] == 1
        assert result["requestedAt"] == "2026-04-18T00:00:00+09:00"
        assert result["requestId"]
        assert result["enqueuedAt"] == "2026-04-18T00:00:00+09:00"
        assert result["reclaimedCount"] == 0
        assert result["requestedBy"] is None
        assert result["retryCount"] == 0

    def test_preserves_existing_fields(self):
        raw = {
            "requestId": "kept-id",
            "userId": 2,
            "requestedAt": "...",
            "retryCount": 3,
            "reclaimedCount": 1,
            "enqueuedAt": "kept-ts",
            "requestedBy": 7,
        }
        result = ensure_envelope(raw)
        assert result["requestId"] == "kept-id"
        assert result["retryCount"] == 3
        assert result["reclaimedCount"] == 1
        assert result["enqueuedAt"] == "kept-ts"
        assert result["requestedBy"] == 7

    def test_does_not_mutate_input(self):
        raw = {"userId": 3}
        result = ensure_envelope(raw)
        assert raw == {"userId": 3}
        assert result is not raw

    def test_coerces_invalid_reclaimed_count_to_zero(self):
        # 외부 producer 가 None/비숫자 를 넣어도 reclaimer int() 파싱 안전
        assert ensure_envelope({"reclaimedCount": None})["reclaimedCount"] == 0
        assert (
            ensure_envelope({"reclaimedCount": "bad"})["reclaimedCount"] == 0
        )
        assert ensure_envelope({"reclaimedCount": 5})["reclaimedCount"] == 5
