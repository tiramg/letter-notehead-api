import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from render import render_pdf


class RenderTests(unittest.TestCase):
    def test_rejected_import_returns_warned_preview(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'score.pdf'
            calls = []
            def run(command, **kwargs):
                calls.append(command)
                if len(calls) == 1:
                    return subprocess.CompletedProcess(command, 40, '', '')
                target.write_bytes(b'%PDF-test')
                return subprocess.CompletedProcess(command, 0, '', '')
            warnings = []
            with patch('render.subprocess.run', side_effect=run):
                self.assertEqual(render_pdf('score.mxl', target, binary='/renderer', warnings=warnings), target)
            self.assertNotIn('-f', calls[0])
            self.assertIn('-f', calls[1])
            self.assertEqual(len(warnings), 1)

    def test_crash_is_not_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('render.subprocess.run', return_value=subprocess.CompletedProcess([], 139, '', 'crash')) as run:
                with self.assertRaises(RuntimeError):
                    render_pdf('score.mxl', Path(directory)/'score.pdf', binary='/renderer', warnings=[])
                self.assertEqual(run.call_count, 1)

    def test_strict_caller_does_not_force_import(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('render.subprocess.run', return_value=subprocess.CompletedProcess([], 40, '', 'invalid measure')) as run:
                with self.assertRaises(RuntimeError):
                    render_pdf('score.mxl', Path(directory)/'score.pdf', binary='/renderer')
                self.assertEqual(run.call_count, 1)

    def test_failed_retry_does_not_claim_success(self):
        with tempfile.TemporaryDirectory() as directory:
            warnings = []
            with patch('render.subprocess.run', return_value=subprocess.CompletedProcess([], 40, '', 'invalid measure')):
                with self.assertRaises(RuntimeError):
                    render_pdf('score.mxl', Path(directory)/'score.pdf', binary='/renderer', warnings=warnings)
            self.assertEqual(warnings, [])
