import shutil
import subprocess
from pathlib import Path
from unittest import skipUnless
from django.conf import settings
from django.test import SimpleTestCase

SHELL = shutil.which('sh')
if not SHELL:
    candidate = Path('C:/Program Files/Git/bin/sh.exe')
    SHELL = str(candidate) if candidate.exists() else None


@skipUnless(SHELL, 'Git shell is required to test the local push safeguard.')
class MainPushSafeguardTests(SimpleTestCase):
    def run_hook(self, value):
        return subprocess.run([SHELL, str(settings.BASE_DIR / '.githooks' / 'pre-push')], input=value, text=True, capture_output=True, check=False)

    def test_main_updates_and_force_pushes_are_blocked(self):
        for local in ('refs/heads/main', 'refs/heads/feature/test'):
            result = self.run_hook(f'{local} {"a"*40} refs/heads/main {"b"*40}\n')
            self.assertEqual(result.returncode,1)
            self.assertIn('Direct pushes to main are blocked',result.stderr)

    def test_main_deletion_is_blocked(self):
        result=self.run_hook(f'(delete) {"0"*40} refs/heads/main {"b"*40}\n')
        self.assertEqual(result.returncode,1)

    def test_feature_push_and_feature_deletion_are_allowed(self):
        result=self.run_hook(f'refs/heads/feature/test {"a"*40} refs/heads/feature/test {"b"*40}\n(delete) {"0"*40} refs/heads/fix/old {"c"*40}\n')
        self.assertEqual(result.returncode,0,result.stderr)

    def test_multi_ref_push_cannot_hide_a_main_update(self):
        result=self.run_hook(f'refs/heads/feature/test {"a"*40} refs/heads/feature/test {"b"*40}\nrefs/heads/main {"a"*40} refs/heads/main {"b"*40}\n')
        self.assertEqual(result.returncode,1)
