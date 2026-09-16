from unittest.mock import MagicMock, call, patch

from scraping.batch_runner import batch_exit_code, run_in_processes


def _noop(_: int) -> None:
    pass


def _raises(_: int) -> None:
    raise RuntimeError("boom")


class TestRunInProcesses:
    @patch("scraping.batch_runner.multiprocessing.Process")
    def test_starts_every_process_before_joining(self, mock_process_cls):
        """전부 start 한 뒤에 join 하는지.

        순차 start-join 이 되면 병렬성이 사라진다. 이 함수에서 유일하게
        조용히 깨질 수 있는 지점이다.
        """
        manager = MagicMock()
        first, second = MagicMock(), MagicMock()
        manager.attach_mock(first, "first")
        manager.attach_mock(second, "second")
        mock_process_cls.side_effect = [first, second]

        run_in_processes(_noop, [1, 2])

        names = [c[0] for c in manager.mock_calls]
        assert names.index("second.start") < names.index("first.join")

    @patch("scraping.batch_runner.multiprocessing.Process")
    def test_passes_each_arg_to_its_process(self, mock_process_cls):
        """인자 개수만큼 프로세스를 만들고 각 인자를 전달하는지"""
        mock_process_cls.side_effect = [MagicMock(), MagicMock()]

        run_in_processes(_noop, [10, 20])

        assert mock_process_cls.call_args_list == [
            call(target=_noop, args=(10,)),
            call(target=_noop, args=(20,)),
        ]

    def test_real_child_exception_yields_nonzero_exitcode(self):
        """실제 프로세스가 예외로 죽으면 exitcode 가 0 이 아닌지.

        나머지 테스트는 Process 를 통째로 목킹하므로 "자식이 죽으면
        exitcode 로 드러난다" 는 전제 자체는 검증하지 못한다.
        """
        assert run_in_processes(_raises, [1]) == [1]


class TestBatchExitCode:
    def test_returns_one_when_any_child_failed(self):
        """자식이 하나라도 실패하면 1 을 반환하는지"""
        assert batch_exit_code([0, 1]) == 1

    def test_returns_zero_when_all_succeeded(self):
        """전부 성공이면 0 을 반환하는지"""
        assert batch_exit_code([0, 0]) == 0

    def test_treats_none_exitcode_as_failure(self):
        """exitcode 가 None 이면 성공으로 오판하지 않는지"""
        assert batch_exit_code([0, None]) == 1
