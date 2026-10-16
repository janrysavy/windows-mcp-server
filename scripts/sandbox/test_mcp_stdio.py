"""Host transport tests. No desktop API, server process or guest UI is invoked."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from mcp_stdio import publish, read_published


class MappedFileTests(unittest.TestCase):
    def test_sharing_delay_retries_only_the_read(self):
        path = Mock()
        path.read_text.side_effect = [PermissionError(13, "sharing"), FileNotFoundError(), '{"text":"žluťoučký"}']
        with patch("mcp_stdio.time.sleep"):
            value = read_published(path)
        self.assertEqual(json.loads(value)["text"], "žluťoučký")
        self.assertEqual(path.read_text.call_count, 3)

    def test_persistent_access_failure_is_bounded(self):
        path = Mock()
        path.read_text.side_effect = PermissionError(13, "denied")
        now = [0.0]
        with patch("mcp_stdio.time.monotonic", side_effect=lambda: now[0]), \
             patch("mcp_stdio.time.sleep", side_effect=lambda delay: now.__setitem__(0, now[0]+delay)):
            with self.assertRaises(PermissionError):
                read_published(path, timeout=0.1)
        self.assertLess(now[0], 0.14)

    def test_concurrent_stop_publication_has_no_shared_temporary_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "stop.json"
            errors = []

            def writer(value):
                try:
                    for _ in range(20):
                        publish(target, json.dumps({"writer": value}))
                except Exception as exc:
                    errors.append(exc)

            workers = [threading.Thread(target=writer, args=(value,)) for value in (1, 2)]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join()
            self.assertEqual(errors, [])
            self.assertIn(json.loads(target.read_text())["writer"], (1, 2))
            self.assertEqual(list(Path(temporary).glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
