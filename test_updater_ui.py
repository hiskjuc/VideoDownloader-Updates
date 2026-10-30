import sys
import unittest
from unittest.mock import MagicMock, patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

import updater
from version import __version__
from ui.main_window import MainWindow


# Garante uma única instância do QApplication para os testes de interface
app = QApplication.instance() or QApplication(sys.argv)


class TestUpdaterUI(unittest.TestCase):
    def setUp(self):
        # Instancia a janela principal com hooks desativados nos testes para isolamento
        with patch.object(MainWindow, "_setup_window_hook"):
            self.win = MainWindow()

    def tearDown(self):
        self.win.close()

    # 1. Consulta automática executada na inicialização
    def test_startup_check_called(self):
        """Valida que _verificar_atualizacao_automatica inicia a consulta silenciosa e marca _startup_update_checked."""
        self.assertFalse(self.win._startup_update_checked)

        with patch.object(self.win, "verificar_atualizacao") as mock_verificar:
            self.win._verificar_atualizacao_automatica()
            self.assertTrue(self.win._startup_update_checked)
            mock_verificar.assert_called_once_with(silencioso=True)

    # 2. Ausência de verificações duplicadas na inicialização (executa apenas uma vez por inicialização)
    def test_startup_check_runs_only_once(self):
        """Garante que a verificação de inicialização não seja repetida se chamada novamente."""
        with patch.object(self.win, "verificar_atualizacao") as mock_verificar:
            self.win._verificar_atualizacao_automatica()
            self.assertEqual(mock_verificar.call_count, 1)

            # Segunda chamada não deve executar verificar_atualizacao
            self.win._verificar_atualizacao_automatica()
            self.assertEqual(mock_verificar.call_count, 1)

    # 3. Consulta automática ocorre mesmo quando um download de mídia estiver em andamento
    def test_startup_check_initiated_even_during_media_download(self):
        """Garante que a verificação de inicialização seja disparada mesmo com download de mídia ativo."""
        fake_worker = MagicMock()
        fake_worker.isRunning.return_value = True
        self.win.worker = fake_worker

        with patch.object(self.win, "verificar_atualizacao") as mock_verificar:
            self.win._verificar_atualizacao_automatica()
            mock_verificar.assert_called_once_with(silencioso=True)
            self.assertTrue(self.win._startup_update_checked)

    # 4. Impede verificações simultâneas duplicadas se uma já estiver em execução
    def test_verificar_atualizacao_prevent_duplicate_concurrent_runs(self):
        fake_checker = MagicMock()
        fake_checker.isRunning.return_value = True
        self.win.update_checker = fake_checker

        with patch("ui.main_window.UpdateChecker") as mock_checker_cls:
            self.win.verificar_atualizacao(silencioso=True)
            mock_checker_cls.assert_not_called()

    # 4. Apresentação da janela de atualização quando há nova versão e nenhum download ativo
    @patch.object(QMessageBox, "exec", return_value=0)
    def test_on_update_available_dialog_presentation(self, mock_exec):
        """Valida se o diálogo apresenta os textos, versões, resumo e botões corretos."""
        notes = """## O que mudou
- Melhorias na estabilidade dos downloads
- Correções no processamento de vídeos
"""
        with patch.object(self.win, "_iniciar_download_atualizacao") as mock_download:
            self.win._is_silent_update = True
            self.win._on_update_available(
                version="v1.3.0",
                notes=notes,
                installer_url="https://github.com/hiskjuc/VideoDownloader-Updates/releases/download/v1.3.0/VideoDownloader_Setup.exe",
                checksum_url="https://github.com/hiskjuc/VideoDownloader-Updates/releases/download/v1.3.0/checksums.txt",
                api_sha256="abc" * 21 + "a"
            )

            mock_exec.assert_called_once()
            mock_download.assert_not_called()

    # 5. Botão 'Baixar e instalar' inicia o download do instalador
    def test_on_update_available_accept_triggers_download(self):
        notes = "- Correção geral."
        installer_url = "https://github.com/hiskjuc/VideoDownloader-Updates/releases/download/v1.3.0/VideoDownloader_Setup.exe"

        captured_box = []

        def mock_exec_accept(box_self):
            captured_box.append(box_self)
            for b in box_self.buttons():
                if "Baixar" in b.text():
                    box_self._mock_clicked = b
                    break
            return 0

        with patch.object(QMessageBox, "exec", mock_exec_accept), \
             patch.object(QMessageBox, "clickedButton", lambda b: getattr(b, "_mock_clicked", None)), \
             patch.object(self.win, "_iniciar_download_atualizacao") as mock_download:
            self.win._on_update_available(
                version="v1.3.0",
                notes=notes,
                installer_url=installer_url,
                checksum_url="",
                api_sha256=""
            )
            mock_download.assert_called_once_with(installer_url, "", "")
            self.assertEqual(len(captured_box), 1)
            self.assertEqual(captured_box[0].windowTitle(), "Nova versão disponível")
            self.assertIn(f"Versão atual: {__version__.lstrip('vV')}", captured_box[0].text())
            self.assertIn("Nova versão: 1.3.0", captured_box[0].text())
            self.assertIn("O que mudou:\n- Correção geral.", captured_box[0].text())
            self.assertIn("Deseja atualizar agora?", captured_box[0].text())

    # 6. Botão 'Lembrar mais tarde' não inicia o download do instalador
    def test_on_update_available_reject_does_not_trigger_download(self):
        notes = "- Correção geral."
        installer_url = "https://github.com/hiskjuc/VideoDownloader-Updates/releases/download/v1.3.0/VideoDownloader_Setup.exe"

        def mock_exec_reject(box_self):
            for b in box_self.buttons():
                if "Lembrar" in b.text():
                    box_self._mock_clicked = b
                    break
            return 0

        with patch.object(QMessageBox, "exec", mock_exec_reject), \
             patch.object(QMessageBox, "clickedButton", lambda b: getattr(b, "_mock_clicked", None)), \
             patch.object(self.win, "_iniciar_download_atualizacao") as mock_download:
            self.win._on_update_available(
                version="v1.3.0",
                notes=notes,
                installer_url=installer_url,
                checksum_url="",
                api_sha256=""
            )
            mock_download.assert_not_called()

    # 7. Ausência de notificação quando a versão já é a mais recente em verificação silenciosa
    @patch.object(QMessageBox, "information")
    def test_on_no_update_silent_suppresses_notification(self, mock_info):
        self.win._is_silent_update = True
        self.win._on_no_update()
        mock_info.assert_not_called()
        self.assertIsNone(self.win._pending_update)

    # 8. Notificação presente quando o usuário verifica manualmente e já é a mais recente
    @patch.object(QMessageBox, "information")
    def test_on_no_update_manual_shows_notification(self, mock_info):
        self.win._is_silent_update = False
        self.win._on_no_update()
        mock_info.assert_called_once()
        self.assertIsNone(self.win._pending_update)

    # 9. Falha de conexão na inicialização não exibe alerta ao usuário
    @patch.object(QMessageBox, "warning")
    def test_on_update_error_silent_suppresses_alert(self, mock_warning):
        self.win._is_silent_update = True
        self.win._on_update_error("Erro temporário de conexão com o GitHub")
        mock_warning.assert_not_called()
        self.assertIsNone(self.win._pending_update)

    # 10. Falha de conexão em verificação manual exibe alerta com detalhes
    @patch.object(QMessageBox, "warning")
    def test_on_update_error_manual_shows_alert(self, mock_warning):
        self.win._is_silent_update = False
        self.win._on_update_error("Falha de rede")
        mock_warning.assert_called_once()
        self.assertIsNone(self.win._pending_update)

    # 11. Atualização durante download de mídia ativo: fica pendente e é apresentada ao término
    def test_update_during_active_media_download_is_deferred_until_finish(self):
        fake_worker = MagicMock()
        fake_worker.isRunning.return_value = True
        self.win.worker = fake_worker

        captured_dialogs = []

        def mock_exec(box_self):
            captured_dialogs.append(box_self)
            return 0

        with patch.object(QMessageBox, "exec", mock_exec):
            # 1. Chegada da atualização com download ativo
            self.win._on_update_available(
                version="v1.3.0",
                notes="- Novidades.",
                installer_url="https://github.com/hiskjuc/VideoDownloader-Updates/releases/download/v1.3.0/VideoDownloader_Setup.exe",
                checksum_url="",
                api_sha256=""
            )

            # O diálogo NÃO deve ser exibido durante o download
            self.assertEqual(len(captured_dialogs), 0)
            self.assertIsNotNone(self.win._pending_update)
            self.assertEqual(self.win._pending_update[0], "v1.3.0")

            # 2. O download é finalizado com sucesso
            fake_worker.isRunning.return_value = False
            self.win.finalizar_download("sucesso", "OK")

            # O diálogo pendente DEVE ser apresentado agora
            self.assertEqual(len(captured_dialogs), 1)
            # A notificação pendente deve ter sido consumida
            self.assertIsNone(self.win._pending_update)

    # 12. Impede apresentação duplicada da mesma atualização pendente
    def test_pending_update_not_duplicated_on_multiple_finishes(self):
        fake_worker = MagicMock()
        fake_worker.isRunning.return_value = True
        self.win.worker = fake_worker

        captured_dialogs = []

        with patch.object(QMessageBox, "exec", lambda box: captured_dialogs.append(box) or 0):
            self.win._on_update_available("v1.3.0", "Notas", "http://...", "", "")
            fake_worker.isRunning.return_value = False

            # Primeiro término apresenta
            self.win.finalizar_download("sucesso", "OK")
            self.assertEqual(len(captured_dialogs), 1)

            # Segundo término subsequente NÃO deve reabrir a janela
            self.win.finalizar_download("sucesso", "OK")
            self.assertEqual(len(captured_dialogs), 1)

    # 13. Notificação pendente não é exibida se o aplicativo estiver em processo de fechamento
    def test_pending_update_not_shown_if_closing_pending(self):
        fake_worker = MagicMock()
        fake_worker.isRunning.return_value = True
        self.win.worker = fake_worker

        captured_dialogs = []

        with patch.object(QMessageBox, "exec", lambda box: captured_dialogs.append(box) or 0):
            self.win._on_update_available("v1.3.0", "Notas", "http://...", "", "")
            self.assertIsNotNone(self.win._pending_update)

            # Simula que o usuário está fechando a aplicação
            self.win._closing_pending = True
            fake_worker.isRunning.return_value = False
            self.win.finalizar_download("cancelado", "Fechando")

            # Não exibe diálogo enquanto o app fecha
            self.assertEqual(len(captured_dialogs), 0)


if __name__ == "__main__":
    unittest.main()
