"""Never mix fictional uploaded test images with a developer's real media folder."""
from tempfile import TemporaryDirectory
from django.test.runner import DiscoverRunner
from django.test import override_settings


class PrivateMediaRunner(DiscoverRunner):
    def setup_test_environment(self,**kwargs):
        super().setup_test_environment(**kwargs)
        self.media_dir=TemporaryDirectory(prefix='fbt-test-media-')
        self.media_settings=override_settings(MEDIA_ROOT=self.media_dir.name)
        self.media_settings.enable()

    def teardown_test_environment(self,**kwargs):
        try:
            self.media_settings.disable()
            self.media_dir.cleanup()
        finally:super().teardown_test_environment(**kwargs)
