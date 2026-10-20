import os
import hashlib
import tempfile
import shutil
import unittest
from unittest.mock import patch, MagicMock
import requests

import updater
from updater import UpdateChecker, UpdateDownloader, parse_version


class FakeResponse:
    """Objeto de resposta simulado para testes determinísticos de streaming e redirecionamento."""
    def __init__(self, status_code=200, json_data=None, text="", chunks=None, headers=None, url="", history=None):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text
        self._chunks = chunks if chunks is not None else []
        self.headers = headers if headers is not None else {}
        self.url = url
        self.history = history if history is not None else []
        self.closed = False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"HTTP Error {self.status_code}")

    def json(self):
        if isinstance(self._json_data, Exception):
            raise self._json_data
        return self._json_data

    def iter_content(self, chunk_size=8192):
        for chunk in self._chunks:
            yield chunk

    def close(self):
        self.closed = True


class TestUpdater(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_vd_updater_")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # 1. Versões válidas
    def test_01_parse_version_valid(self):
        self.assertEqual(parse_version("1.0.0"), (1, 0, 0))
        self.assertEqual(parse_version("v1.1.0"), (1, 1, 0))
        self.assertEqual(parse_version("V2.10.3"), (2, 10, 3))
        self.assertEqual(parse_version("2.0"), (2, 0, 0))
        self.assertTrue(parse_version("1.10.0") > parse_version("1.2.0"))

    # 2. Versões inválidas rejeitadas com ValueError
    def test_02_parse_version_invalid(self):
        for invalid in ["invalid", "", "   ", "v", "v1.0.0-beta", "1.0.0-rc1", "1.a.0", "v1..0", None, 123]:
            with self.subTest(version=invalid):
                with self.assertRaises(ValueError):
                    parse_version(invalid)

    # 3. Ausência de configuração do repositório
    def test_03_unconfigured_repository(self):
        with patch.object(updater, "GITHUB_OWNER", ""):
            checker = UpdateChecker()
            errors = []
            checker.error.connect(errors.append)
            checker.run()
            self.assertEqual(len(errors), 1)
            self.assertIn("não configurado", errors[0].lower())

    # 4. Ausência de atualização (mesma versão ou inferior)
    def test_04_no_update_available(self):
        resp = FakeResponse(json_data={"tag_name": "v1.0.0", "assets": []})
        with patch.object(updater, "GITHUB_OWNER", "UserA"), \
             patch.object(updater, "__version__", "1.0.0"), \
             patch("updater.requests.get", return_value=resp):
            checker = UpdateChecker()
            no_update_called = []
            checker.no_update.connect(lambda: no_update_called.append(True))
            checker.run()
            self.assertTrue(no_update_called)

    # 5. Tag inválida na release não é tratada como (0, 0, 0) nem oferece atualização
    def test_05_invalid_remote_tag_rejected(self):
        resp = FakeResponse(json_data={"tag_name": "v1.2.0-beta1", "assets": []})
        with patch.object(updater, "GITHUB_OWNER", "UserA"), \
             patch.object(updater, "__version__", "1.0.0"), \
             patch("updater.requests.get", return_value=resp):
            checker = UpdateChecker()
            avail = []
            errors = []
            checker.update_available.connect(lambda *a: avail.append(a))
            checker.error.connect(errors.append)
            checker.run()
            self.assertEqual(len(avail), 0)
            self.assertEqual(len(errors), 1)

    # 6. Prerelease ou draft ignorados
    def test_06_prerelease_ignored(self):
        resp = FakeResponse(json_data={"tag_name": "v2.0.0", "prerelease": True, "assets": []})
        with patch.object(updater, "GITHUB_OWNER", "UserA"), \
             patch.object(updater, "__version__", "1.0.0"), \
             patch("updater.requests.get", return_value=resp):
            checker = UpdateChecker()
            no_upd = []
            checker.no_update.connect(lambda: no_upd.append(True))
            checker.run()
            self.assertTrue(no_upd)

    # 7. Nova versão disponível usando digest SHA-256 direto da API
    def test_07_update_available_with_api_digest(self):
        valid_hash = "a" * 64
        resp = FakeResponse(json_data={
            "tag_name": "v1.1.0",
            "body": "Notas da v1.1.0",
            "assets": [{
                "name": "VideoDownloader_Setup.exe",
                "browser_download_url": "https://github.com/UserA/VideoDownloader-Updates/releases/download/v1.1.0/VideoDownloader_Setup.exe",
                "digest": f"sha256:{valid_hash}"
            }]
        })
        with patch.object(updater, "GITHUB_OWNER", "UserA"), \
             patch.object(updater, "__version__", "1.0.0"), \
             patch("updater.requests.get", return_value=resp):
            checker = UpdateChecker()
            avail = []
            checker.update_available.connect(lambda *a: avail.append(a))
            checker.run()
            self.assertEqual(len(avail), 1)
            self.assertEqual(avail[0][0], "v1.1.0")
            self.assertEqual(avail[0][4], valid_hash)

    # 8. Nova versão disponível usando checksums.txt
    def test_08_update_available_with_checksums_file(self):
        resp = FakeResponse(json_data={
            "tag_name": "v1.1.0",
            "body": "Notas",
            "assets": [
                {
                    "name": "VideoDownloader_Setup.exe",
                    "browser_download_url": "https://github.com/UserA/VideoDownloader-Updates/releases/download/v1.1.0/VideoDownloader_Setup.exe"
                },
                {
                    "name": "checksums.txt",
                    "browser_download_url": "https://github.com/UserA/VideoDownloader-Updates/releases/download/v1.1.0/checksums.txt"
                }
            ]
        })
        with patch.object(updater, "GITHUB_OWNER", "UserA"), \
             patch.object(updater, "__version__", "1.0.0"), \
             patch("updater.requests.get", return_value=resp):
            checker = UpdateChecker()
            avail = []
            checker.update_available.connect(lambda *a: avail.append(a))
            checker.run()
            self.assertEqual(len(avail), 1)
            self.assertEqual(avail[0][4], "")

    # 9. Erro de rede na consulta
    def test_09_network_error_on_check(self):
        with patch.object(updater, "GITHUB_OWNER", "UserA"), \
             patch("updater.requests.get", side_effect=requests.exceptions.ConnectionError("Sem internet")):
            checker = UpdateChecker()
            errors = []
            checker.error.connect(errors.append)
            checker.run()
            self.assertEqual(len(errors), 1)

    # 10. Release sem o asset VideoDownloader_Setup.exe
    def test_10_missing_installer_asset(self):
        resp = FakeResponse(json_data={
            "tag_name": "v1.2.0",
            "assets": [{"name": "outro_arquivo.zip", "browser_download_url": "https://github.com/UserA/VideoDownloader-Updates/releases/download/v1.2.0/outro.zip"}]
        })
        with patch.object(updater, "GITHUB_OWNER", "UserA"), \
             patch.object(updater, "__version__", "1.0.0"), \
             patch("updater.requests.get", return_value=resp):
            checker = UpdateChecker()
            errors = []
            checker.error.connect(errors.append)
            checker.run()
            self.assertEqual(len(errors), 1)
            self.assertIn("VideoDownloader_Setup.exe", errors[0])

    # 11. URL inicial não confiável (HTTP ou outro domínio/repositório)
    def test_11_untrusted_initial_url(self):
        with patch.object(updater, "GITHUB_OWNER", "UserA"):
            for bad_url in [
                "http://github.com/UserA/VideoDownloader-Updates/releases/download/v1.1.0/VideoDownloader_Setup.exe",
                "https://evil.example.com/UserA/VideoDownloader-Updates/releases/download/v1.1.0/VideoDownloader_Setup.exe",
                "https://github.com/OutroUser/VideoDownloader-Updates/releases/download/v1.1.0/VideoDownloader_Setup.exe"
            ]:
                dl = UpdateDownloader(bad_url, "", self.temp_dir, expected_digest="a" * 64)
                errors = []
                dl.error.connect(errors.append)
                dl.run()
                self.assertEqual(len(errors), 1)

    # 12. Redirecionamento para host malicioso bloqueado
    def test_12_untrusted_redirect_blocked(self):
        installer_url = "https://github.com/UserA/VideoDownloader-Updates/releases/download/v1.1.0/VideoDownloader_Setup.exe"
        bad_redirect_resp = FakeResponse(
            chunks=[b"abc"],
            headers={"content-length": "3"},
            url="https://malicious-cdn.example.com/VideoDownloader_Setup.exe"
        )
        with patch.object(updater, "GITHUB_OWNER", "UserA"), \
             patch("updater.requests.get", return_value=bad_redirect_resp):
            dl = UpdateDownloader(installer_url, "", self.temp_dir, expected_digest=hashlib.sha256(b"abc").hexdigest())
            errors = []
            finished = []
            dl.error.connect(errors.append)
            dl.finished_download.connect(finished.append)
            dl.run()
            self.assertEqual(len(finished), 0)
            self.assertEqual(len(errors), 1)
            self.assertEqual(os.listdir(self.temp_dir), [])

    # 13. Checksum ausente
    def test_13_missing_checksum(self):
        installer_url = "https://github.com/UserA/VideoDownloader-Updates/releases/download/v1.1.0/VideoDownloader_Setup.exe"
        with patch.object(updater, "GITHUB_OWNER", "UserA"):
            dl = UpdateDownloader(installer_url, "", self.temp_dir, expected_digest="")
            errors = []
            dl.error.connect(errors.append)
            dl.run()
            self.assertEqual(len(errors), 1)

    # 14. Checksum malformado no manifesto
    def test_14_malformed_checksum_in_manifest(self):
        installer_url = "https://github.com/UserA/VideoDownloader-Updates/releases/download/v1.1.0/VideoDownloader_Setup.exe"
        checksum_url = "https://github.com/UserA/VideoDownloader-Updates/releases/download/v1.1.0/checksums.txt"
        manifest_resp = FakeResponse(
            text="hash_invalido_123  VideoDownloader_Setup.exe\n",
            url="https://objects.githubusercontent.com/checksums.txt"
        )
        with patch.object(updater, "GITHUB_OWNER", "UserA"), \
             patch("updater.requests.get", return_value=manifest_resp):
            dl = UpdateDownloader(installer_url, checksum_url, self.temp_dir)
            errors = []
            dl.error.connect(errors.append)
            dl.run()
            self.assertEqual(len(errors), 1)
            self.assertIn("manifesto", errors[0].lower())

    # 15. Checksum incorreto (manifesto válido + conteúdo divergente -> arquivo descartado)
    def test_15_incorrect_checksum_discards_file(self):
        installer_url = "https://github.com/UserA/VideoDownloader-Updates/releases/download/v1.1.0/VideoDownloader_Setup.exe"
        checksum_url = "https://github.com/UserA/VideoDownloader-Updates/releases/download/v1.1.0/checksums.txt"
        wrong_valid_hash = "b" * 64
        payload = b"conteudo_corrompido_ou_adulterado"

        manifest_resp = FakeResponse(
            text=f"{wrong_valid_hash}  VideoDownloader_Setup.exe\n",
            url="https://objects.githubusercontent.com/checksums.txt"
        )
        installer_resp = FakeResponse(
            chunks=[payload],
            headers={"content-length": str(len(payload))},
            url="https://objects.githubusercontent.com/VideoDownloader_Setup.exe"
        )

        with patch.object(updater, "GITHUB_OWNER", "UserA"), \
             patch("updater.requests.get", side_effect=[manifest_resp, installer_resp]):
            dl = UpdateDownloader(installer_url, checksum_url, self.temp_dir)
            errors = []
            finished = []
            dl.error.connect(errors.append)
            dl.finished_download.connect(finished.append)
            dl.run()

            self.assertEqual(len(finished), 0, "Não deve emitir finished_download quando o SHA-256 diverge.")
            self.assertEqual(len(errors), 1)
            self.assertIn("sha-256", errors[0].lower())
            self.assertEqual(os.listdir(self.temp_dir), [], "Arquivo temporário inválido deve ser removido.")

    # 16. Checksum correto e preservação de arquivos existentes na pasta temporária
    def test_16_valid_checksum_success_and_unique_temp_file(self):
        installer_url = "https://github.com/UserA/VideoDownloader-Updates/releases/download/v1.1.0/VideoDownloader_Setup.exe"
        checksum_url = "https://github.com/UserA/VideoDownloader-Updates/releases/download/v1.1.0/checksums.txt"
        payload = b"binario_oficial_do_instalador_123456"
        expected_hash = hashlib.sha256(payload).hexdigest()

        # Cria um arquivo pré-existente na pasta temporária para garantir que não será sobrescrito
        pre_existing = os.path.join(self.temp_dir, "VideoDownloader_Update.exe")
        with open(pre_existing, "wb") as f:
            f.write(b"arquivo_antigo_intocavel")

        manifest_resp = FakeResponse(
            text=f"{expected_hash}  VideoDownloader_Setup.exe\n",
            url="https://objects.githubusercontent.com/checksums.txt"
        )
        installer_resp = FakeResponse(
            chunks=[payload[:10], payload[10:]],
            headers={"content-length": str(len(payload))},
            url="https://objects.githubusercontent.com/VideoDownloader_Setup.exe"
        )

        with patch.object(updater, "GITHUB_OWNER", "UserA"), \
             patch("updater.requests.get", side_effect=[manifest_resp, installer_resp]):
            dl = UpdateDownloader(installer_url, checksum_url, self.temp_dir)
            errors = []
            finished = []
            dl.error.connect(errors.append)
            dl.finished_download.connect(finished.append)
            dl.run()

            self.assertEqual(len(errors), 0)
            self.assertEqual(len(finished), 1)
            downloaded_path = finished[0]
            self.assertNotEqual(os.path.abspath(downloaded_path), os.path.abspath(pre_existing))
            with open(downloaded_path, "rb") as f:
                self.assertEqual(f.read(), payload)
            with open(pre_existing, "rb") as f:
                self.assertEqual(f.read(), b"arquivo_antigo_intocavel")

    # 17. Download sem Content-Length
    def test_17_download_without_content_length(self):
        installer_url = "https://github.com/UserA/VideoDownloader-Updates/releases/download/v1.1.0/VideoDownloader_Setup.exe"
        payload = b"instalador_sem_header_content_length"
        expected_hash = hashlib.sha256(payload).hexdigest()

        installer_resp = FakeResponse(
            chunks=[payload[:12], payload[12:]],
            headers={},
            url="https://objects.githubusercontent.com/VideoDownloader_Setup.exe"
        )

        with patch.object(updater, "GITHUB_OWNER", "UserA"), \
             patch("updater.requests.get", return_value=installer_resp):
            dl = UpdateDownloader(installer_url, "", self.temp_dir, expected_digest=expected_hash)
            finished = []
            progress_events = []
            dl.finished_download.connect(finished.append)
            dl.progress.connect(progress_events.append)
            dl.run()

            self.assertEqual(len(finished), 1)
            self.assertIn(0, progress_events)
            self.assertEqual(progress_events[-1], 100)

    # 18. Download incompleto (bytes recebidos < Content-Length)
    def test_18_incomplete_download_detected(self):
        installer_url = "https://github.com/UserA/VideoDownloader-Updates/releases/download/v1.1.0/VideoDownloader_Setup.exe"
        partial_payload = b"apenas_parte_dos_bytes"
        hash_of_partial = hashlib.sha256(partial_payload).hexdigest()

        installer_resp = FakeResponse(
            chunks=[partial_payload],
            headers={"content-length": "9999"},
            url="https://objects.githubusercontent.com/VideoDownloader_Setup.exe"
        )

        with patch.object(updater, "GITHUB_OWNER", "UserA"), \
             patch("updater.requests.get", return_value=installer_resp):
            dl = UpdateDownloader(installer_url, "", self.temp_dir, expected_digest=hash_of_partial)
            errors = []
            finished = []
            dl.error.connect(errors.append)
            dl.finished_download.connect(finished.append)
            dl.run()

            self.assertEqual(len(finished), 0)
            self.assertEqual(len(errors), 1)
            self.assertIn("incompleto", errors[0].lower())
            self.assertEqual(os.listdir(self.temp_dir), [])

    # 19. Falha HTTP durante o download do instalador
    def test_19_http_error_on_installer_download(self):
        installer_url = "https://github.com/UserA/VideoDownloader-Updates/releases/download/v1.1.0/VideoDownloader_Setup.exe"
        http_err_resp = FakeResponse(status_code=503, url=installer_url)

        with patch.object(updater, "GITHUB_OWNER", "UserA"), \
             patch("updater.requests.get", return_value=http_err_resp):
            dl = UpdateDownloader(installer_url, "", self.temp_dir, expected_digest="a" * 64)
            errors = []
            dl.error.connect(errors.append)
            dl.run()

            self.assertEqual(len(errors), 1)
            self.assertEqual(os.listdir(self.temp_dir), [])

    # 20. Cancelamento cooperativo durante o download em blocos
    def test_20_cancel_download_cleans_up_temp_file(self):
        installer_url = "https://github.com/UserA/VideoDownloader-Updates/releases/download/v1.1.0/VideoDownloader_Setup.exe"
        dl_ref = []

        def chunk_generator():
            yield b"bloco_1"
            if dl_ref:
                dl_ref[0].cancel()
            yield b"bloco_2"

        installer_resp = FakeResponse(
            chunks=chunk_generator(),
            headers={},
            url="https://objects.githubusercontent.com/VideoDownloader_Setup.exe"
        )

        with patch.object(updater, "GITHUB_OWNER", "UserA"), \
             patch("updater.requests.get", return_value=installer_resp):
            dl = UpdateDownloader(installer_url, "", self.temp_dir, expected_digest="a" * 64)
            dl_ref.append(dl)
            errors = []
            finished = []
            dl.error.connect(errors.append)
            dl.finished_download.connect(finished.append)
            dl.run()

            self.assertEqual(len(finished), 0)
            self.assertEqual(len(errors), 1)
            self.assertIn("cancelado", errors[0].lower())
            self.assertEqual(os.listdir(self.temp_dir), [])


if __name__ == "__main__":
    unittest.main()