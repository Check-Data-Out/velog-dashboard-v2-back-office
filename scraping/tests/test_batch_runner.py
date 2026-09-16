from unittest.mock import MagicMock, call, patch

from scraping.batch_runner import finalize_batch, run_in_processes


def _noop(_: int) -> None:
    pass


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

        assert manager.mock_calls == [
            call.first.start(),
            call.second.start(),
            call.first.join(),
            call.second.join(),
        ]

    @patch("scraping.batch_runner.multiprocessing.Process")
    def test_passes_each_arg_to_its_process(self, mock_process_cls):
        """인자 개수만큼 프로세스를 만들고 각 인자를 전달하는지"""
        mock_process_cls.side_effect = [MagicMock(), MagicMock()]

        run_in_processes(_noop, [10, 20])

        assert mock_process_cls.call_args_list == [
            call(target=_noop, args=(10,)),
            call(target=_noop, args=(20,)),
        ]

    @patch("scraping.batch_runner.multiprocessing.Process")
    def test_returns_exitcodes(self, mock_process_cls):
        """join 후 각 프로세스의 exitcode 를 반환하는지"""
        first, second = MagicMock(), MagicMock()
        first.exitcode, second.exitcode = 0, 1
        mock_process_cls.side_effect = [first, second]

        assert run_in_processes(_noop, [1, 2]) == [0, 1]


class TestFinalizeBatch:
    def test_notifies_before_reporting_failure(self):
        """실패가 있어도 알림을 먼저 보내는지.

        이번 장애의 핵심이 "실패했는데 알림이 안 갔다" 였으므로 순서를
        고정한다.
        """
        notifier = MagicMock()

        assert finalize_batch([0, 1], notifier) == 1
        notifier.assert_called_once()

    def test_returns_zero_when_all_succeeded(self):
        """전부 성공이면 0 을 반환하는지"""
        notifier = MagicMock()

        assert finalize_batch([0, 0], notifier) == 0
        notifier.assert_called_once()

    def test_treats_none_exitcode_as_failure(self):
        """exitcode 가 None 이면 성공으로 오판하지 않는지"""
        assert finalize_batch([0, None], MagicMock()) == 1
