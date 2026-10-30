import sys
import unittest
from unittest.mock import patch, MagicMock

from PySide6.QtCore import Qt, QSettings
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow
from ui.theme import get_theme_palette, get_theme_stylesheet


app = QApplication.instance() or QApplication(sys.argv)


class TestUIRedesign(unittest.TestCase):
    def setUp(self):
        self.settings = QSettings("VideoDownloaderApp", "VideoDownloader")
        self.original_theme = self.settings.value("theme", None)
        with patch.object(MainWindow, "_setup_window_hook"):
            self.win = MainWindow()

    def tearDown(self):
        self.win.close()
        if self.original_theme is not None:
            self.settings.setValue("theme", self.original_theme)
        else:
            self.settings.remove("theme")

    def test_initial_theme_default_is_light_or_saved(self):
        """Valida que o tema inicial é light ou o tema salvo previamente."""
        self.assertIn(self.win.current_theme, ("light", "dark"))
        self.assertEqual(self.win.theme_toggle.theme, self.win.current_theme)

    def test_theme_toggle_switches_and_persists(self):
        """Valida alternância instantânea entre Light e Dark Mode e persistência via QSettings."""
        # 1. Altera para Dark Mode
        self.win.set_theme("dark")
        self.assertEqual(self.win.current_theme, "dark")
        self.assertEqual(self.settings.value("theme"), "dark")
        self.assertEqual(self.win.theme_toggle.theme, "dark")
        self.assertEqual(self.win.bg_content_widget.theme, "dark")

        # 2. Altera para Light Mode
        self.win.set_theme("light")
        self.assertEqual(self.win.current_theme, "light")
        self.assertEqual(self.settings.value("theme"), "light")
        self.assertEqual(self.win.theme_toggle.theme, "light")
        self.assertEqual(self.win.bg_content_widget.theme, "light")

    def test_theme_restored_on_reopening(self):
        """Valida que uma nova instância de MainWindow restaura o tema salvo no QSettings."""
        self.settings.setValue("theme", "dark")
        with patch.object(MainWindow, "_setup_window_hook"):
            win2 = MainWindow()
            self.assertEqual(win2.current_theme, "dark")
            self.assertEqual(win2.theme_toggle.theme, "dark")
            win2.close()

    def test_sidebar_navigation_three_views(self):
        """Valida a navegação e ativação das 3 páginas da barra lateral."""
        # Página 0: Início
        self.win._navegar_para(0)
        self.assertEqual(self.win.stack.currentIndex(), 0)
        self.assertTrue(self.win.btn_nav_home.is_active)
        self.assertFalse(self.win.btn_nav_settings.is_active)
        self.assertFalse(self.win.btn_nav_info.is_active)

        # Página 1: Configurações
        self.win._navegar_para(1)
        self.assertEqual(self.win.stack.currentIndex(), 1)
        self.assertFalse(self.win.btn_nav_home.is_active)
        self.assertTrue(self.win.btn_nav_settings.is_active)
        self.assertFalse(self.win.btn_nav_info.is_active)

        # Página 2: Informações
        self.win._navegar_para(2)
        self.assertEqual(self.win.stack.currentIndex(), 2)
        self.assertFalse(self.win.btn_nav_home.is_active)
        self.assertFalse(self.win.btn_nav_settings.is_active)
        self.assertTrue(self.win.btn_nav_info.is_active)

    def test_all_expected_widgets_exist_and_configured(self):
        """Garante a existência de todos os componentes de controle exigidos pelo redesign."""
        self.assertIsNotNone(self.win.input_url)
        self.assertIsNotNone(self.win.input_pasta)
        self.assertIsNotNone(self.win.btn_escolher)
        self.assertIsNotNone(self.win.combo_formato)
        self.assertIsNotNone(self.win.btn_baixar)
        self.assertIsNotNone(self.win.lbl_status)
        self.assertIsNotNone(self.win.progress_bar)
        self.assertIsNotNone(self.win.lbl_percent)
        self.assertIsNotNone(self.win.theme_toggle)

        # Valida placeholders e valores iniciais
        self.assertEqual(self.win.input_url.placeholderText(), "Cole aqui o link do vídeo...")
        self.assertTrue(len(self.win.input_pasta.text()) > 0)
        self.assertTrue(self.win.combo_formato.count() > 0)
        self.assertIn("BAIXAR", self.win.btn_baixar.text().upper())

    def test_format_selection_persists(self):
        """Valida que selecionar um formato no combobox atualiza o QSettings."""
        # Encontra o índice de mp3
        mp3_idx = -1
        for i in range(self.win.combo_formato.count()):
            if self.win.combo_formato.itemData(i) == "mp3":
                mp3_idx = i
                break
        if mp3_idx != -1:
            self.win.combo_formato.setCurrentIndex(mp3_idx)
            self.assertEqual(self.settings.value("output_format"), "mp3")

    def test_status_label_color_updates_with_theme_and_type(self):
        """Valida que aplicar_status altera cores conforme o tipo e o tema."""
        self.win.set_theme("light")
        self.win.aplicar_status("● Sucesso", "sucesso")
        self.assertIn("#10B981", self.win.lbl_status.styleSheet())

        self.win.aplicar_status("● Erro", "erro")
        self.assertIn("#EF4444", self.win.lbl_status.styleSheet())

        self.win.set_theme("dark")
        self.win.aplicar_status("● Normal", "normal")
        self.assertIn("#388BFD", self.win.lbl_status.styleSheet())


if __name__ == "__main__":
    unittest.main()
