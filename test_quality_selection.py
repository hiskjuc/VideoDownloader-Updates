import os
import sys
import tempfile
import pathlib
import unittest
from unittest.mock import patch, MagicMock

from PySide6.QtCore import Qt, QSettings
from PySide6.QtWidgets import QApplication

from downloader import (
    build_format_options, extract_media_info, download_video, publish_unique_file,
    get_video_dimensions, upscale_video,
    VIDEO_RESOLUTIONS, AUDIO_BITRATES, VIDEO_FORMATS, AUDIO_FORMATS
)
from ui.main_window import MainWindow, MediaInfoWorker, DownloadWorker


app = QApplication.instance() or QApplication(sys.argv)


class TestQualityOptionsBackend(unittest.TestCase):
    def test_build_format_options_video_resolutions(self):
        """Valida que build_format_options gera seletores de resolução para formatos de vídeo."""
        for res in ["2160p", "1440p", "1080p", "720p", "480p", "360p"]:
            h = int(res[:-1])
            opts_mp4 = build_format_options("mp4", video_quality=res)
            self.assertEqual(opts_mp4.get("merge_output_format"), "mp4")
            self.assertIn(f"height={h}", opts_mp4["format"])
            self.assertIn("bestaudio", opts_mp4["format"])

            opts_webm = build_format_options("webm", video_quality=res)
            self.assertEqual(opts_webm.get("merge_output_format"), "webm")
            self.assertIn(f"height={h}", opts_webm["format"])

            opts_mkv = build_format_options("mkv", video_quality=res)
            self.assertEqual(opts_mkv.get("merge_output_format"), "mkv")
            self.assertIn(f"height={h}", opts_mkv["format"])

    def test_build_format_options_video_best_default(self):
        """Valida comportamento padrão de melhor qualidade de vídeo."""
        opts = build_format_options("mp4", video_quality="best")
        self.assertEqual(opts.get("merge_output_format"), "mp4")
        self.assertIn("bestvideo", opts["format"])
        self.assertIn("bestaudio", opts["format"])

    def test_build_format_options_audio_bitrates(self):
        """Valida aplicação de taxas de bits para formatos de áudio."""
        for bitrate in ["320k", "256k", "192k", "128k", "96k"]:
            clean_b = bitrate.replace("k", "")
            for fmt in ["mp3", "m4a", "opus"]:
                opts = build_format_options(fmt, audio_quality=bitrate)
                self.assertEqual(opts["format"], "bestaudio/best")
                pp = opts["postprocessors"][0]
                self.assertEqual(pp["key"], "FFmpegExtractAudio")
                self.assertEqual(pp["preferredcodec"], fmt)
                self.assertEqual(pp["preferredquality"], clean_b)

    def test_build_format_options_audio_lossless_untouched(self):
        """Formatos lossless (wav, flac) não devem receber preferredquality mesmo se informada."""
        for fmt in ["wav", "flac"]:
            opts = build_format_options(fmt, audio_quality="320k")
            pp = opts["postprocessors"][0]
            self.assertNotIn("preferredquality", pp)

    def test_build_format_options_audio_best_copy(self):
        """Melhor qualidade para M4A e Opus utiliza '0' para permitir stream copy sem recodificação."""
        for fmt in ["m4a", "opus"]:
            opts = build_format_options(fmt, audio_quality="best")
            pp = opts["postprocessors"][0]
            self.assertEqual(pp.get("preferredquality"), "0")

    @patch("downloader.yt_dlp.YoutubeDL")
    def test_extract_media_info_resolutions_filtering(self, mock_ydl_cls):
        """Valida que extract_media_info identifica e filtra apenas resoluções presentes e inclui a URL."""
        mock_instance = MagicMock()
        mock_ydl_cls.return_value.__enter__.return_value = mock_instance
        mock_instance.extract_info.return_value = {
            "title": "Vídeo Teste HD",
            "duration": 120,
            "extractor": "youtube",
            "formats": [
                {"vcodec": "avc1", "acodec": "none", "height": 1080, "width": 1920},
                {"vcodec": "avc1", "acodec": "none", "height": 720, "width": 1280},
                {"vcodec": "avc1", "acodec": "none", "height": 480, "width": 854},
                {"vcodec": "none", "acodec": "mp4a", "abr": 128},
            ]
        }

        url = "https://example.com/watch?v=123"
        res = extract_media_info(url)
        self.assertTrue(res["sucesso"])
        self.assertEqual(res["url"], url)
        self.assertEqual(res["title"], "Vídeo Teste HD")
        self.assertEqual(res["max_height"], 1080)
        self.assertEqual(res["max_audio_bitrate"], 128)

        # 1080p, 720p, 480p devem estar presentes, mas 2160p (4K) e 1440p (2K) NÃO
        available_keys = [k for k, _ in res["available_resolutions"]]
        self.assertIn("1080p", available_keys)
        self.assertIn("720p", available_keys)
        self.assertIn("480p", available_keys)
        self.assertNotIn("2160p", available_keys)
        self.assertNotIn("1440p", available_keys)

    @patch("downloader.yt_dlp.YoutubeDL")
    def test_download_video_rejects_unavailable_resolution(self, mock_ydl_cls):
        """Valida que solicitar uma resolução indisponível (ex: 2160p em vídeo 720p) reporta erro claro."""
        mock_instance = MagicMock()
        mock_ydl_cls.return_value.__enter__.return_value = mock_instance
        mock_instance.extract_info.return_value = {
            "title": "Vídeo Somente 720p",
            "formats": [
                {"vcodec": "avc1", "acodec": "none", "height": 720, "width": 1280},
                {"vcodec": "avc1", "acodec": "none", "height": 360, "width": 640},
            ]
        }

        status, msg = download_video(
            "https://example.com/video",
            "C:\\Temp",
            output_format="mp4",
            video_quality="2160p"
        )
        self.assertEqual(status, "erro")
        self.assertIn("2160p", msg)
        self.assertIn("não está disponível", msg)
        self.assertIn("máxima disponível: 720p", msg)
        # ydl.download não deve ter sido chamado
        mock_instance.download.assert_not_called()

    @patch("downloader.yt_dlp.YoutubeDL")
    def test_extract_media_info_public_url_without_cookies(self, mock_ydl_cls):
        """Valida que URLs públicas funcionam sem acessar cookies do navegador (evitando erro 7271)."""
        mock_instance = MagicMock()
        mock_ydl_cls.return_value.__enter__.return_value = mock_instance
        mock_instance.extract_info.return_value = {
            "title": "Vídeo Público 1080p",
            "formats": [{"vcodec": "avc1", "acodec": "none", "height": 1080, "width": 1920}]
        }

        res = extract_media_info("https://youtube.com/watch?v=public_video", active_browser="chrome")
        self.assertTrue(res["sucesso"])
        self.assertEqual(res["title"], "Vídeo Público 1080p")
        # Valida que a primeira tentativa para URL pública não incluiu cookiesfrombrowser
        first_call_opts = mock_ydl_cls.call_args[0][0]
        self.assertNotIn("cookiesfrombrowser", first_call_opts)

    def test_extract_media_info_authenticated_content_uses_cookies(self):
        """Valida que URLs com restrição/login recorrem aos cookies do navegador quando disponíveis."""
        call_opts = []
        def mock_ydl(opts):
            call_opts.append(opts)
            mock_inst = MagicMock()
            if "cookiesfrombrowser" not in opts:
                mock_inst.extract_info.side_effect = Exception("Sign in to confirm your age")
            else:
                mock_inst.extract_info.return_value = {
                    "title": "Vídeo com Restrição de Idade",
                    "formats": [{"vcodec": "avc1", "acodec": "none", "height": 720, "width": 1280}]
                }
            m = MagicMock()
            m.__enter__.return_value = mock_inst
            return m

        with patch("downloader.yt_dlp.YoutubeDL", side_effect=mock_ydl):
            res = extract_media_info("https://youtube.com/watch?v=age_gated", active_browser="chrome")
            self.assertTrue(res["sucesso"])
            self.assertEqual(res["title"], "Vídeo com Restrição de Idade")
            self.assertEqual(len(call_opts), 2)
            self.assertNotIn("cookiesfrombrowser", call_opts[0])
            self.assertIn("cookiesfrombrowser", call_opts[1])
            self.assertEqual(call_opts[1]["cookiesfrombrowser"], ("chrome", None, None, None))

    def test_extract_media_info_cookie_lock_handles_gracefully(self):
        """Valida que bloqueio no banco de cookies do Chrome é tratado sem falha não capturada."""
        def mock_ydl(opts):
            mock_inst = MagicMock()
            if "cookiesfrombrowser" not in opts:
                mock_inst.extract_info.side_effect = Exception("Sign in to view this video")
            else:
                # Simula erro 7271 do yt-dlp ao tentar copiar o banco Cookies travado pelo Chrome
                raise Exception("Could not copy Chrome cookie database. See https://github.com/yt-dlp/yt-dlp/issues/7271")
            m = MagicMock()
            m.__enter__.return_value = mock_inst
            return m

        with patch("downloader.yt_dlp.YoutubeDL", side_effect=mock_ydl):
            res = extract_media_info("https://youtube.com/watch?v=locked_video", active_browser="chrome")
            self.assertFalse(res["sucesso"])
            self.assertIn("autenticação", res["mensagem"].lower())
            self.assertIn("chrome", res["mensagem"].lower())

    def test_download_video_cookie_lock_retries_without_cookies(self):
        """Valida que em caso de bloqueio de cookies no download, continua o download sem cookies."""
        call_count = 0
        def mock_ydl(opts):
            nonlocal call_count
            call_count += 1
            if "cookiesfrombrowser" in opts:
                raise Exception("Could not copy Chrome cookie database. See https://github.com/yt-dlp/yt-dlp/issues/7271")
            mock_inst = MagicMock()
            mock_inst.extract_info.return_value = {
                "title": "Vídeo Download Sucesso",
                "formats": [{"vcodec": "avc1", "acodec": "mp4a", "height": 720, "width": 1280}]
            }
            m = MagicMock()
            m.__enter__.return_value = mock_inst
            return m

        with patch("downloader.yt_dlp.YoutubeDL", side_effect=mock_ydl):
            status, msg = download_video("https://example.com/video", r"C:\Temp", active_browser="chrome")
            self.assertEqual(status, "sucesso")
            self.assertEqual(call_count, 2)


class TestQualityOptionsUI(unittest.TestCase):
    def setUp(self):
        self.settings = QSettings("VideoDownloaderApp", "VideoDownloader")
        self.orig_mode = self.settings.value("download_mode", None)
        self.orig_format = self.settings.value("output_format", None)
        self.orig_vq = self.settings.value("video_quality", None)
        self.orig_aq = self.settings.value("audio_quality", None)

        with patch.object(MainWindow, "_setup_window_hook"):
            self.win = MainWindow()

    def tearDown(self):
        self.win.close()
        for key, orig in [
            ("download_mode", self.orig_mode),
            ("output_format", self.orig_format),
            ("video_quality", self.orig_vq),
            ("audio_quality", self.orig_aq),
        ]:
            if orig is not None:
                self.settings.setValue(key, orig)
            else:
                self.settings.remove(key)

    def test_mode_buttons_exist_and_toggle(self):
        """Valida presença dos botões de modo e alternância entre Vídeo e Somente Áudio."""
        self.assertIsNotNone(self.win.btn_mode_video)
        self.assertIsNotNone(self.win.btn_mode_audio)
        self.assertIsNotNone(self.win.combo_qualidade)

        # Alterna para modo Áudio
        self.win.set_mode("audio")
        self.assertEqual(self.win.current_mode, "audio")
        self.assertEqual(self.settings.value("download_mode"), "audio")
        self.assertEqual(self.win.lbl_formato.text(), "Formato de áudio")
        self.assertEqual(self.win.lbl_qualidade.text(), "Qualidade do áudio")

        # Alterna para modo Vídeo
        self.win.set_mode("video")
        self.assertEqual(self.win.current_mode, "video")
        self.assertEqual(self.settings.value("download_mode"), "video")
        self.assertEqual(self.win.lbl_formato.text(), "Formato de vídeo")
        self.assertEqual(self.win.lbl_qualidade.text(), "Resolução")

    def test_combobox_populated_according_to_mode(self):
        """Valida que combo_formato e combo_qualidade se ajustam conforme o modo ativo."""
        # Modo Vídeo
        self.win.set_mode("video")
        video_formats = [self.win.combo_formato.itemData(i) for i in range(self.win.combo_formato.count())]
        self.assertIn("mp4", video_formats)
        self.assertIn("mkv", video_formats)
        self.assertNotIn("mp3", video_formats)

        video_qualities = [self.win.combo_qualidade.itemData(i) for i in range(self.win.combo_qualidade.count())]
        self.assertIn("best", video_qualities)
        self.assertIn("1080p", video_qualities)
        self.assertNotIn("320k", video_qualities)

        # Modo Áudio
        self.win.set_mode("audio")
        audio_formats = [self.win.combo_formato.itemData(i) for i in range(self.win.combo_formato.count())]
        self.assertIn("mp3", audio_formats)
        self.assertIn("m4a", audio_formats)
        self.assertNotIn("mp4", audio_formats)

        audio_qualities = [self.win.combo_qualidade.itemData(i) for i in range(self.win.combo_qualidade.count())]
        self.assertIn("best", audio_qualities)
        self.assertIn("320k", audio_qualities)
        self.assertNotIn("1080p", audio_qualities)

    def test_lossless_audio_disables_bitrate_combo(self):
        """Selecionar formato sem perdas (WAV/FLAC) desabilita combobox de taxa de bits."""
        self.win.set_mode("audio")
        # Encontra índice de WAV
        wav_idx = -1
        for i in range(self.win.combo_formato.count()):
            if self.win.combo_formato.itemData(i) == "wav":
                wav_idx = i
                break
        self.assertNotEqual(wav_idx, -1)
        self.win.combo_formato.setCurrentIndex(wav_idx)
        self.assertFalse(self.win.combo_qualidade.isEnabled())
        self.assertEqual(self.win.combo_qualidade.currentData(), "best")

        # Volta para MP3 -> deve reabilitar combo de qualidade
        mp3_idx = -1
        for i in range(self.win.combo_formato.count()):
            if self.win.combo_formato.itemData(i) == "mp3":
                mp3_idx = i
                break
        self.assertNotEqual(mp3_idx, -1)
        self.win.combo_formato.setCurrentIndex(mp3_idx)
        self.assertTrue(self.win.combo_qualidade.isEnabled())


class TestDynamicQualityAndUpscalingUI(unittest.TestCase):
    def setUp(self):
        self.settings = QSettings("VideoDownloaderApp", "VideoDownloader")
        with patch.object(MainWindow, "_setup_window_hook"):
            self.win = MainWindow()

    def tearDown(self):
        self.win.close()

    def test_quality_card_initially_hidden(self):
        """Ao abrir o aplicativo, o cartão de qualidade e o contêiner de upscaling devem permanecer ocultos."""
        self.assertTrue(self.win.subcard_qualidade.isHidden())
        self.assertTrue(self.win.container_upscaling.isHidden())

    def test_url_debounce_triggers_analysis(self):
        """Inserir uma URL válida inicia o timer de debounce para análise."""
        self.win.input_url.setText("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertTrue(self.win._url_debounce_timer.isActive())

    def test_analysis_shows_discreet_indicator(self):
        """Durante a análise da URL, um indicador discreto de carregamento deve ser exibido."""
        self.win.input_url.setText("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        with patch("ui.main_window.MediaInfoWorker") as mock_worker_cls:
            mock_worker = MagicMock()
            mock_worker_cls.return_value = mock_worker
            self.win._consultar_info_url()

            self.assertIn("Analisando", self.win.lbl_status.text())
            self.assertFalse(self.win.lbl_stats.isHidden())
            # Barra indeterminada
            self.assertEqual(self.win.progress_bar.minimum(), 0)
            self.assertEqual(self.win.progress_bar.maximum(), 0)
            mock_worker.start.assert_called_once()

    def test_media_info_ready_displays_quality_card_and_selects_best(self):
        """Após a análise com sucesso, exibe o cartão de qualidade com a melhor opção selecionada por padrão."""
        target_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        self.win.input_url.setText(target_url)

        fake_info = {
            "sucesso": True,
            "url": target_url,
            "title": "Vídeo Teste Sucesso",
            "available_resolutions": [("720p", "720p (HD)"), ("480p", "480p")],
            "max_height": 720,
            "max_audio_bitrate": 128
        }
        self.win._on_media_info_ready(fake_info)

        # O subcard de qualidade deve estar visível
        self.assertFalse(self.win.subcard_qualidade.isHidden())
        # A barra volta para range normal (0, 100)
        self.assertEqual(self.win.progress_bar.maximum(), 100)
        self.assertEqual(self.win.progress_bar.value(), 0)
        self.assertFalse(self.win.lbl_stats.isVisible())
        # Melhor qualidade ('best') selecionada por padrão (índice 0)
        self.assertEqual(self.win.combo_qualidade.currentIndex(), 0)
        self.assertEqual(self.win.combo_qualidade.currentData(Qt.UserRole), "best")
        # Link identificado no status
        self.assertIn("Link identificado", self.win.lbl_status.text())

    def test_media_info_error_discreet_notification(self):
        """Se a análise falhar, informa discretamente sem caixas de erro bloqueantes e mantém cartão oculto."""
        self.win.input_url.setText("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.win._on_media_info_error("Falha ao conectar")

        self.assertTrue(self.win.subcard_qualidade.isHidden())
        self.assertTrue(self.win.container_upscaling.isHidden())
        self.assertEqual(self.win.progress_bar.maximum(), 100)
        self.assertFalse(self.win.lbl_stats.isVisible())
        self.assertIn("Não foi possível identificar as qualidades", self.win.lbl_status.text())

    def test_changing_url_hides_quality_and_upscaling_immediately(self):
        """Se o usuário alterar ou apagar a URL, oculta imediatamente as opções da URL anterior."""
        target_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        self.win.input_url.setText(target_url)

        fake_info = {
            "sucesso": True,
            "url": target_url,
            "title": "Vídeo Teste",
            "available_resolutions": [("720p", "720p (HD)")],
            "max_height": 720
        }
        self.win._on_media_info_ready(fake_info)
        self.assertFalse(self.win.subcard_qualidade.isHidden())

        # Usuário altera a URL
        self.win.input_url.setText("https://www.youtube.com/watch?v=outro_video")
        self.assertTrue(self.win.subcard_qualidade.isHidden())
        self.assertTrue(self.win.container_upscaling.isHidden())
        self.assertIsNone(self.win.current_media_info)

    def test_race_condition_prevention_discards_stale_results(self):
        """Resultados assíncronos de URLs antigas não devem sobrescrever a URL atual do usuário."""
        self.win.input_url.setText("https://www.youtube.com/watch?v=NOVA_URL")

        stale_info = {
            "sucesso": True,
            "url": "https://www.youtube.com/watch?v=URL_ANTIGA",
            "title": "Vídeo Antigo",
            "available_resolutions": [("1080p", "1080p (Full HD)")],
            "max_height": 1080
        }
        self.win._on_media_info_ready(stale_info)

        # O resultado obsoleto deve ter sido descartado
        self.assertTrue(self.win.subcard_qualidade.isHidden())
        self.assertIsNone(self.win.current_media_info)

    def test_download_clears_stale_media_info_if_url_mismatch(self):
        """Garante que nunca inicia download usando informações de uma URL diferente da informada."""
        self.win.current_media_info = {"title": "Vídeo Velho", "max_height": 720}
        self.win._analyzed_url = "https://example.com/video1"

        self.win.input_url.setText("https://example.com/video2")
        self.win.input_pasta.setText("C:\\Temp")

        with patch("ui.main_window.DownloadWorker") as mock_worker_cls:
            self.win.iniciar_download()
            mock_worker_cls.assert_called_once()
            # current_media_info deve ter sido anulado pelo mismatch
            self.assertIsNone(self.win.current_media_info)

    def test_upscaling_options_strictly_superior_resolutions(self):
        """Valida que o seletor de upscaling oferece estritamente resoluções superiores à resolução original."""
        target_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        self.win.set_mode("video")
        self.win.input_url.setText(target_url)

        # Cenário 1: Vídeo de 720p -> Deve oferecer apenas 1080p, 1440p e 2160p (NÃO 720p nem 480p)
        info_720 = {
            "sucesso": True,
            "url": target_url,
            "title": "Vídeo 720p",
            "available_resolutions": [("720p", "720p (HD)")],
            "max_height": 720
        }
        self.win._on_media_info_ready(info_720)
        self.assertFalse(self.win.container_upscaling.isHidden())
        upscale_options = [self.win.combo_upscaling.itemData(i) for i in range(self.win.combo_upscaling.count())]
        self.assertEqual(upscale_options, ["1080p", "1440p", "2160p"])

        # Cenário 2: Vídeo de 1080p -> Deve oferecer apenas 1440p e 2160p
        info_1080 = {
            "sucesso": True,
            "url": target_url,
            "title": "Vídeo 1080p",
            "available_resolutions": [("1080p", "1080p (Full HD)")],
            "max_height": 1080
        }
        self.win._on_media_info_ready(info_1080)
        upscale_options_1080 = [self.win.combo_upscaling.itemData(i) for i in range(self.win.combo_upscaling.count())]
        self.assertEqual(upscale_options_1080, ["1440p", "2160p"])

        # Cenário 3: Vídeo de 2160p (4K) -> Sem resoluções superiores suportadas, contêiner deve ficar oculto
        info_4k = {
            "sucesso": True,
            "url": target_url,
            "title": "Vídeo 4K",
            "available_resolutions": [("2160p", "2160p (4K)")],
            "max_height": 2160
        }
        self.win._on_media_info_ready(info_4k)
        self.assertTrue(self.win.container_upscaling.isHidden())

    def test_upscaling_hidden_in_audio_mode(self):
        """No modo de áudio, a opção de upscaling de resolução deve permanecer oculta."""
        target_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        self.win.set_mode("audio")
        self.win.input_url.setText(target_url)

        fake_info = {
            "sucesso": True,
            "url": target_url,
            "title": "Áudio Mídia",
            "available_resolutions": [("720p", "720p (HD)")],
            "max_height": 720
        }
        self.win._on_media_info_ready(fake_info)
        self.assertTrue(self.win.container_upscaling.isHidden())

    def test_upscaling_checkbox_toggles_combo(self):
        """Marcar a caixa 'Melhorar resolução (Upscaling)' habilita a combobox e exibe o aviso de CPU."""
        self.assertFalse(self.win.combo_upscaling.isEnabled())
        self.assertTrue(self.win.box_upscale_warning.isHidden())
        self.win.chk_upscaling.setChecked(True)
        self.assertTrue(self.win.combo_upscaling.isEnabled())
        self.assertFalse(self.win.box_upscale_warning.isHidden())
        self.win.chk_upscaling.setChecked(False)
        self.assertFalse(self.win.combo_upscaling.isEnabled())
        self.assertTrue(self.win.box_upscale_warning.isHidden())

    def test_upscaling_cpu_warning_content_and_themes(self):
        """Valida textos informativos e suporte a Light e Dark Mode no aviso de processamento intenso."""
        self.assertIn("Atenção: processamento intenso", self.win.lbl_warning_title.text())
        self.assertIn("CPU", self.win.lbl_warning_body.text())
        self.assertIn("temperatura do computador", self.win.lbl_warning_body.text())
        self.assertIn("desempenho de outros aplicativos", self.win.lbl_warning_body.text())

        # Teste em Light Mode
        self.win.set_theme("light")
        self.assertFalse(self.win.lbl_warning_icon.pixmap().isNull())

        # Teste em Dark Mode
        self.win.set_theme("dark")
        self.assertFalse(self.win.lbl_warning_icon.pixmap().isNull())

    def test_iniciar_download_passes_upscale_quality(self):
        """Quando o upscaling está ativado e visível, o destino de upscaling é repassado ao DownloadWorker."""
        target_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        self.win.set_mode("video")
        self.win.input_url.setText(target_url)
        self.win.input_pasta.setText("C:\\Temp")

        fake_info = {
            "sucesso": True,
            "url": target_url,
            "title": "Vídeo 720p",
            "available_resolutions": [("720p", "720p (HD)")],
            "max_height": 720
        }
        self.win._on_media_info_ready(fake_info)

        # Ativa upscaling
        self.win.chk_upscaling.setChecked(True)
        # Seleciona 1080p
        idx_1080 = -1
        for i in range(self.win.combo_upscaling.count()):
            if self.win.combo_upscaling.itemData(i) == "1080p":
                idx_1080 = i
                break
        self.assertNotEqual(idx_1080, -1)
        self.win.combo_upscaling.setCurrentIndex(idx_1080)

        with patch("ui.main_window.DownloadWorker") as mock_worker_cls:
            self.win.btn_baixar.click()
            mock_worker_cls.assert_called_once()
            _, kwargs = mock_worker_cls.call_args
            self.assertEqual(kwargs.get("upscale_quality"), "1080p")

        self.win.finalizar_download("sucesso", "")
        self.assertTrue(self.win.chk_upscaling.isEnabled())
        self.assertTrue(self.win.combo_upscaling.isEnabled())


class TestUpscaleBackendLogic(unittest.TestCase):
    @patch("downloader.subprocess.Popen")
    @patch("downloader.get_video_dimensions")
    def test_upscale_video_skips_if_target_le_original(self, mock_dims, mock_popen):
        """upscale_video não reprocessa se a resolução do arquivo já for maior ou igual ao alvo."""
        mock_dims.return_value = (1920, 1080)
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(b"dummy")
            tmp_path = tmp.name

        try:
            ok, msg = upscale_video(tmp_path, target_res="720p")
            self.assertTrue(ok)
            self.assertIn("já é maior ou igual", msg)
            mock_popen.assert_not_called()
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    @patch("downloader.subprocess.Popen")
    @patch("downloader.get_video_dimensions")
    def test_upscale_video_executes_lanczos_with_audio_copy(self, mock_dims, mock_popen):
        """Valida montagem do comando FFmpeg com filtro Lanczos, proporções e -c:a copy."""
        mock_dims.return_value = (854, 480)
        mock_proc = MagicMock()
        mock_proc.poll.side_effect = [None, 0]
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(b"original_video_data")
            tmp_path = pathlib.Path(tmp.name)

        temp_target = tmp_path.with_name(f"{tmp_path.stem}.upscaled_temp{tmp_path.suffix}")

        def side_effect_replace():
            temp_target.write_bytes(b"upscaled_video_data")

        try:
            # Simula que o processo gerou o arquivo de saída temporário
            mock_proc.poll.side_effect = lambda: (side_effect_replace(), 0)[1]

            ok, _ = upscale_video(tmp_path, target_res="720p")
            self.assertTrue(ok)
            mock_popen.assert_called_once()
            cmd_executed = mock_popen.call_args[0][0]
            # Valida scale=-2:720:flags=lanczos
            self.assertIn("scale=-2:720:flags=lanczos", cmd_executed)
            # Valida -c:a copy
            self.assertIn("-c:a", cmd_executed)
            idx_ca = cmd_executed.index("-c:a")
            self.assertEqual(cmd_executed[idx_ca + 1], "copy")
            # Valida libx264
            self.assertIn("libx264", cmd_executed)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
            if temp_target.exists():
                temp_target.unlink()

    @patch("downloader.subprocess.Popen")
    @patch("downloader.get_video_dimensions")
    def test_upscale_video_vertical_aspect_ratio(self, mock_dims, mock_popen):
        """Valida que vídeo vertical (h > w) utiliza scale={target}:-2:flags=lanczos."""
        mock_dims.return_value = (480, 854)
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(b"data")
            tmp_path = pathlib.Path(tmp.name)
        temp_target = tmp_path.with_name(f"{tmp_path.stem}.upscaled_temp{tmp_path.suffix}")

        try:
            mock_proc.poll.side_effect = lambda: (temp_target.write_bytes(b"upscaled"), 0)[1]
            ok, _ = upscale_video(tmp_path, target_res="1080p")
            self.assertTrue(ok)
            cmd_executed = mock_popen.call_args[0][0]
            self.assertIn("scale=1080:-2:flags=lanczos", cmd_executed)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
            if temp_target.exists():
                temp_target.unlink()

    @patch("downloader.subprocess.Popen")
    @patch("downloader.get_video_dimensions")
    def test_upscale_cancellation_cleans_temp_and_preserves_original(self, mock_dims, mock_popen):
        """Em cancelamento, mata FFmpeg, remove arquivo temporário e preserva o original intacto."""
        mock_dims.return_value = (854, 480)
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.kill = MagicMock()
        mock_proc.wait = MagicMock()
        mock_popen.return_value = mock_proc

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(b"original_intact_content")
            tmp_path = pathlib.Path(tmp.name)

        temp_target = tmp_path.with_name(f"{tmp_path.stem}.upscaled_temp{tmp_path.suffix}")
        temp_target.write_bytes(b"partial_upscale_content")

        try:
            is_cancelled = lambda: True
            ok, msg = upscale_video(tmp_path, target_res="720p", is_cancelled=is_cancelled)
            self.assertFalse(ok)
            self.assertIn("cancelado", msg.lower())
            mock_proc.kill.assert_called_once()
            # Arquivo temporário deve ter sido excluído
            self.assertFalse(temp_target.exists())
            # Original deve permanecer intacto
            self.assertTrue(tmp_path.exists())
            self.assertEqual(tmp_path.read_bytes(), b"original_intact_content")
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
            if temp_target.exists():
                temp_target.unlink()




class TestFileOverwriteProtectionAndResolutionSelection(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dest_folder = pathlib.Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_build_format_options_max_resolution_limit(self):
        """Valida que build_format_options nunca solicita resoluções superiores à selecionada."""
        for res in ["2160p", "1440p", "1080p", "720p", "480p", "360p"]:
            h = int(res[:-1])
            opts = build_format_options("mp4", video_quality=res)
            fmt_str = opts["format"]
            self.assertIn(f"height={h}", fmt_str)
            self.assertIn(f"height<={h}", fmt_str)
            # Não deve conter limitações inferiores rígidas que forcem fallback indevido
            self.assertNotIn("height>", fmt_str)

    def test_publish_unique_file_sequential_numbering(self):
        """Valida geração de sufixos numéricos sequenciais: Video.mp4, Video (1).mp4, Video (2).mp4."""
        temp1 = self.dest_folder / "temp1.tmp"
        temp1.write_text("conteúdo 1", encoding="utf-8")
        out1 = publish_unique_file(temp1, self.dest_folder, "Meu Video", "mp4")
        self.assertEqual(out1.name, "Meu Video.mp4")
        self.assertEqual(out1.read_text(encoding="utf-8"), "conteúdo 1")

        temp2 = self.dest_folder / "temp2.tmp"
        temp2.write_text("conteúdo 2", encoding="utf-8")
        out2 = publish_unique_file(temp2, self.dest_folder, "Meu Video", "mp4")
        self.assertEqual(out2.name, "Meu Video (1).mp4")
        self.assertEqual(out2.read_text(encoding="utf-8"), "conteúdo 2")

        temp3 = self.dest_folder / "temp3.tmp"
        temp3.write_text("conteúdo 3", encoding="utf-8")
        out3 = publish_unique_file(temp3, self.dest_folder, "Meu Video", "mp4")
        self.assertEqual(out3.name, "Meu Video (2).mp4")
        self.assertEqual(out3.read_text(encoding="utf-8"), "conteúdo 3")

        # Verifica se todos os 3 arquivos existem simultaneamente intactos
        self.assertTrue(out1.exists())
        self.assertTrue(out2.exists())
        self.assertTrue(out3.exists())

    def test_publish_unique_file_preserves_existing_files(self):
        """Garante que nenhum arquivo preexistente seja sobrescrito ou alterado."""
        p_orig = self.dest_folder / "Tutorial.mp4"
        p_orig.write_text("conteúdo original intacto", encoding="utf-8")

        temp = self.dest_folder / "novo_download.tmp"
        temp.write_text("novo conteúdo", encoding="utf-8")

        published = publish_unique_file(temp, self.dest_folder, "Tutorial", "mp4")
        self.assertEqual(published.name, "Tutorial (1).mp4")
        self.assertEqual(p_orig.read_text(encoding="utf-8"), "conteúdo original intacto")
        self.assertEqual(published.read_text(encoding="utf-8"), "novo conteúdo")

    def test_publish_unique_file_concurrent_threads_safety(self):
        """Garante que múltiplos downloads concorrentes nunca causem colisão de nomes."""
        import concurrent.futures

        num_threads = 12
        def worker(thread_idx):
            tmp = self.dest_folder / f"worker_{thread_idx}.tmp"
            tmp.write_text(f"thread_{thread_idx}", encoding="utf-8")
            return publish_unique_file(tmp, self.dest_folder, "VideoConcorrente", "mp4")

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker, i) for i in range(num_threads)]
            results = [f.result() for f in futures]

        result_names = [p.name for p in results]
        # Todos os nomes gerados devem ser únicos (sem duplicação nem colisão)
        self.assertEqual(len(set(result_names)), num_threads)
        expected_names = {"VideoConcorrente.mp4"} | {f"VideoConcorrente ({i}).mp4" for i in range(1, num_threads)}
        self.assertEqual(set(result_names), expected_names)

    def test_different_formats_same_stem_do_not_collide(self):
        """Formatos diferentes (ex: mp4 e mp3) com o mesmo nome base coexistem sem colisão."""
        tmp_video = self.dest_folder / "tmp_v.tmp"
        tmp_video.write_bytes(b"video_bytes")
        out_v = publish_unique_file(tmp_video, self.dest_folder, "Musica", "mp4")

        tmp_audio = self.dest_folder / "tmp_a.tmp"
        tmp_audio.write_bytes(b"audio_bytes")
        out_a = publish_unique_file(tmp_audio, self.dest_folder, "Musica", "mp3")

        self.assertEqual(out_v.name, "Musica.mp4")
        self.assertEqual(out_a.name, "Musica.mp3")

        # Próximo vídeo deve se chamar Musica (1).mp4
        tmp_v2 = self.dest_folder / "tmp_v2.tmp"
        tmp_v2.write_bytes(b"video2_bytes")
        out_v2 = publish_unique_file(tmp_v2, self.dest_folder, "Musica", "mp4")
        self.assertEqual(out_v2.name, "Musica (1).mp4")

    def test_cancellation_preserves_existing_completed_files(self):
        """Valida que o cancelamento de um download limpa temporários sem afetar arquivos existentes."""
        existing_file = self.dest_folder / "MeuFilme.mp4"
        existing_file.write_bytes(b"filme_completo_intacto")

        # Simula arquivos temporários de um download que será cancelado
        def fake_download_with_cancel(opts):
            outtmpl = opts.get("outtmpl", "")
            temp_path = pathlib.Path(outtmpl.replace("%(title)s", "MeuFilme").replace("%(ext)s", "mp4"))
            temp_path.write_bytes(b"parcial...")
            from downloader import DownloadCancelled
            raise DownloadCancelled("Cancelado pelo usuario de teste")

        with patch("downloader.yt_dlp.YoutubeDL") as mock_ydl:
            mock_inst = MagicMock()
            mock_inst.extract_info.return_value = {"title": "MeuFilme", "formats": [{"height": 720, "vcodec": "avc1"}]}
            mock_inst.download.side_effect = lambda urls: fake_download_with_cancel(mock_ydl.call_args[0][0])
            mock_ydl.return_value.__enter__.return_value = mock_inst

            status, msg = download_video("https://example.com/video", str(self.dest_folder), output_format="mp4")
            self.assertEqual(status, "cancelado")

        # O arquivo original pré-existente deve continuar intacto
        self.assertTrue(existing_file.exists())
        self.assertEqual(existing_file.read_bytes(), b"filme_completo_intacto")
        # Nenhum arquivo temporário deve ter sobrado
        all_files = list(self.dest_folder.glob("*"))
        self.assertEqual(all_files, [existing_file])

    def test_download_video_sequential_naming_integration(self):
        """Valida a integração fim-a-fim de download_video salvando múltiplos arquivos com mesmo título."""
        def fake_download(opts):
            outtmpl = opts.get("outtmpl", "")
            final_path = pathlib.Path(outtmpl.replace("%(title)s", "Apresentacao").replace("%(ext)s", "mp4"))
            final_path.write_text("conteudo baixado", encoding="utf-8")

        with patch("downloader.yt_dlp.YoutubeDL") as mock_ydl:
            mock_inst = MagicMock()
            mock_inst.extract_info.return_value = {"title": "Apresentacao", "formats": [{"height": 1080, "vcodec": "avc1"}]}
            mock_inst.download.side_effect = lambda urls: fake_download(mock_ydl.call_args[0][0])
            mock_ydl.return_value.__enter__.return_value = mock_inst

            status1, _ = download_video("https://example.com/video", str(self.dest_folder), output_format="mp4")
            self.assertEqual(status1, "sucesso")
            self.assertTrue((self.dest_folder / "Apresentacao.mp4").exists())

            status2, _ = download_video("https://example.com/video", str(self.dest_folder), output_format="mp4")
            self.assertEqual(status2, "sucesso")
            self.assertTrue((self.dest_folder / "Apresentacao.mp4").exists())
            self.assertTrue((self.dest_folder / "Apresentacao (1).mp4").exists())

            status3, _ = download_video("https://example.com/video", str(self.dest_folder), output_format="mp4")
            self.assertEqual(status3, "sucesso")
            self.assertTrue((self.dest_folder / "Apresentacao.mp4").exists())
            self.assertTrue((self.dest_folder / "Apresentacao (1).mp4").exists())
            self.assertTrue((self.dest_folder / "Apresentacao (2).mp4").exists())


if __name__ == "__main__":
    unittest.main()

