"""배치 스크립트가 공유하는 멀티프로세싱 실행 헬퍼.

`aggregate_batch` 와 `aggregate_target_batch` 가 같은 코드를 중복하고
있었고, 두 스크립트 모두 `import setup_django` 때문에 테스트에서
import 할 수 없어 검증 대상 밖에 있었다. 순수 함수로 분리해 양쪽이
공유하고 테스트도 가능하게 한다.
"""

import multiprocessing
from collections.abc import Callable


def run_in_processes[T](
    target: Callable[[T], None], arg_list: list[T]
) -> list[int | None]:
    """각 인자로 프로세스를 띄우고 join 후 exitcode 목록을 반환한다.

    병렬성을 위해 전부 start 한 뒤에 join 한다. exitcode 는 join 전이나
    미기동 상태에서 None 일 수 있어 그대로 노출한다.
    """
    processes = []
    for arg in arg_list:
        process = multiprocessing.Process(target=target, args=(arg,))
        process.start()
        processes.append(process)

    for process in processes:
        process.join()

    return [process.exitcode for process in processes]
