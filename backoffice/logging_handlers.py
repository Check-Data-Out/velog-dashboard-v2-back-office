import gzip
import os
import shutil
from logging.handlers import TimedRotatingFileHandler


# https://docs.python.org/3/howto/logging-cookbook.html 참조
class GzipTimedRotatingFileHandler(TimedRotatingFileHandler):
    """gzip 압축을 지원하는 TimedRotatingFileHandler, 자정 로테이션 시 이전 로그 파일을 gzip 압축하는 핸들러."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.namer = self._gzip_namer
        self.rotator = self._gzip_rotator

    @staticmethod
    def _gzip_namer(name: str) -> str:
        return name + ".gz"

    @staticmethod
    def _gzip_rotator(source: str, dest: str) -> None:
        with open(source, "rb") as f_in:
            with gzip.open(dest, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
        os.remove(source)
