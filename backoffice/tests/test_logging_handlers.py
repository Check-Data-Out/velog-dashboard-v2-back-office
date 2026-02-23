import gzip
import os
import tempfile

from backoffice.logging_handlers import GzipTimedRotatingFileHandler


class TestGzipTimedRotatingFileHandler:
    def test_gzip_namer_appends_gz_extension(self):
        result = GzipTimedRotatingFileHandler._gzip_namer("app.log.2026-02-22")
        assert result == "app.log.2026-02-22.gz"

    def test_gzip_rotator_compresses_and_removes_source(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = os.path.join(tmpdir, "app.log")
            dest = os.path.join(tmpdir, "app.log.2026-02-22.gz")
            original_content = b"test log line\n" * 100

            with open(source, "wb") as f:
                f.write(original_content)

            GzipTimedRotatingFileHandler._gzip_rotator(source, dest)

            assert not os.path.exists(source)
            assert os.path.exists(dest)

            with gzip.open(dest, "rb") as f:
                assert f.read() == original_content

    def test_handler_has_namer_and_rotator_set(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "test.log")
            handler = GzipTimedRotatingFileHandler(filename=log_file)

            assert handler.namer is not None
            assert handler.rotator is not None
            handler.close()
