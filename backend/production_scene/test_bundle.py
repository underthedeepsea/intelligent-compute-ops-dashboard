import io
import json
from pathlib import Path
import tempfile
import zipfile
from django.test import SimpleTestCase, TestCase, override_settings
from django.core.management import call_command
from django.core.management.base import CommandError
from .bundle_core import validate_bundle, install_payload


class BundleSafetyTests(SimpleTestCase):
    def invalid_zip(self, entries):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'data.zip'
            with zipfile.ZipFile(file, 'w') as out:
                for name, content in entries:
                    out.writestr(name, content)
            with self.assertRaises((ValueError, KeyError)):
                validate_bundle(file)

    def test_traversal_is_rejected(self):
        self.invalid_zip([('payload/../../outside', b'bad')])

    def test_unlisted_file_is_rejected(self):
        self.invalid_zip([('manifest.json', json.dumps({'format': 'compute-dashboard-local-demo-v1', 'files': []})),
                          ('payload/extra', b'bad')])

    def test_wrong_digest_is_rejected(self):
        self.invalid_zip([('manifest.json', json.dumps({'format': 'compute-dashboard-local-demo-v1',
                         'files': [{'path': 'file', 'size': 3, 'sha256': '0' * 64}]})), ('payload/file', b'bad')])

    def test_symlink_in_zip_is_rejected(self):
        link = zipfile.ZipInfo('payload/link')
        link.external_attr = 0o120777 << 16
        self.invalid_zip([(link, b'/outside')])

    def test_check_writes_nothing_and_apply_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'data'
            result = install_payload({'a/file': b'local'}, root)
            self.assertFalse(result['applied'])
            self.assertFalse(root.exists())
            self.assertFalse(install_payload({'a/file': b'local'}, root, apply=True)['already_installed'])
            self.assertTrue(install_payload({'a/file': b'local'}, root, apply=True)['already_installed'])

    def test_all_conflicts_checked_before_any_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'existing').write_bytes(b'owned')
            with self.assertRaises(ValueError):
                install_payload({'new': b'data', 'existing': b'different'}, root, apply=True)
            self.assertFalse((root/'new').exists())
            self.assertEqual((root/'existing').read_bytes(), b'owned')

    def test_destination_symlinks_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'link').symlink_to(root, target_is_directory=True)
            with self.assertRaises(ValueError):
                install_payload({'link/outside': b'data'}, root, apply=True)
            self.assertFalse((root/'outside').exists())


class OptionalDataTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.override = override_settings(PRODUCTION_SCENE_DATA_DIR=self.temp.name)
        self.override.enable()
        self.addCleanup(self.override.disable)

    def test_normal_catalog_and_live_routes_work_without_demo(self):
        for url in ['/api/v1/production-scene/catalog', '/api/v1/production-scene/live/overview',
                    '/api/v1/production-scene/live/services', '/api/v1/production-scene/live/critical-apps']:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_missing_source_returns_structured_error(self):
        response = self.client.get('/api/v1/production-scene/source')
        self.assertEqual(response.status_code, 503)
        self.assertIn('DEMO_DATA_MISSING', response.content.decode())

    @override_settings(PRODUCTION_SCENE_REPLAY_ENABLED=False)
    def test_closed_replay_does_not_need_data(self):
        self.assertEqual(self.client.get('/api/v1/production-scene/replay/dataset').status_code, 404)

    @override_settings(PRODUCTION_SCENE_REPLAY_ENABLED=True)
    def test_open_replay_without_package_does_not_fallback(self):
        response = self.client.get('/api/v1/production-scene/replay/dataset')
        self.assertEqual(response.status_code, 503)
        self.assertIn('DEMO_DATA_MISSING', response.content.decode())

    def test_missing_bundle_prepare_fails_without_writes(self):
        from .models import CatalogImport
        with self.assertRaises(CommandError):
            call_command('prepare_szg_scene', stdout=io.StringIO())
        self.assertEqual(CatalogImport.objects.count(), 0)
