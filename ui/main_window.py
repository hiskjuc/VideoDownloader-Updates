import pathlib
import time
import os
import ctypes
from ctypes import wintypes
from collections import deque
import tempfile
import traceback

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QProgressBar, QComboBox,
    QMenuBar, QMessageBox, QProgressDialog, QStackedWidget,
    QFrame, QSizePolicy, QScrollArea
)
from PySide6.QtCore import QThread, Signal, Qt, QSettings, QTimer, QUrl
from PySide6.QtGui import (
    QCloseEvent, QStandardItemModel, QStandardItem, QFont, QAction,
    QDesktopServices, QIcon
)

from downloader import download_video, get_fallback_browser
from version import __version__, GITHUB_OWNER, GITHUB_REPO
from updater import UpdateChecker, UpdateDownloader, format_release_notes

from ui.icons import (
    get_app_icon_pixmap, get_link_icon, get_folder_icon,
    get_folder_pixmap, get_document_icon, get_document_pixmap,
    get_download_button_icon
)
from ui.theme import get_theme_palette, get_theme_stylesheet
from ui.widgets import (
    ContentBackgroundWidget, ThemeToggleWidget, SidebarNavButton
)

EVENT_SYSTEM_FOREGROUND = 0x0003
WINEVENT_OUTOFCONTEXT = 0x0000

WINEVENTPROC = ctypes.WINFUNCTYPE(
    None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND, wintypes.LONG,
    wintypes.LONG, wintypes.DWORD, wintypes.DWORD
)


class DownloadWorker(QThread):
    finished_signal = Signal(str, str)
    progress_signal = Signal(dict)

    def __init__(self, url, dest_folder, output_format="mp4", active_browser=None):
        super().__init__()
        self.url = url
        self.dest_folder = dest_folder
        self.output_format = output_format
        self.active_browser = active_browser
        self._is_cancelled = False
        self.speed_history = deque(maxlen=30)
        self.last_text_update = 0

    def cancelar(self):
        self._is_cancelled = True

    def checar_cancelamento(self):
        return self._is_cancelled

    def run(self):
        try:
            status, mensagem = download_video(
                self.url,
                self.dest_folder,
                output_format=self.output_format,
                progress_callback=self.enviar_progresso,
                is_cancelled=self.checar_cancelamento,
                active_browser=self.active_browser
            )
        except Exception as e:
            # Garante que a interface sempre saia do estado de download,
            # registrando o erro em vez de ignorá-lo silenciosamente.
            traceback.print_exc()
            status, mensagem = "erro", f"Falha inesperada no download: {e}"
        self.finished_signal.emit(status, mensagem)

    def format_speed(self, bps):
        if bps >= 1048576:
            return f"{bps/1048576:.1f} MB/s"
        if bps >= 1024:
            return f"{bps/1024:.1f} KB/s"
        return f"{bps:.0f} B/s"

    def format_eta(self, secs):
        secs = int(secs)
        m, s = divmod(secs, 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    def enviar_progresso(self, raw_dados):
        status = raw_dados.get("status")
        if status == "extracting":
            self.progress_signal.emit({"status": "extracting"})
            return

        if status == "downloading":
            percent = raw_dados.get("percent", 0)
            current_speed = raw_dados.get("speed")
            total = raw_dados.get("total_bytes")
            downloaded = raw_dados.get("downloaded_bytes")

            if current_speed is not None:
                self.speed_history.append(current_speed)
            avg_speed = sum(self.speed_history) / len(self.speed_history) if self.speed_history else 0

            now = time.time()
            update_text = False
            text_to_show = ""

            if (now - self.last_text_update) >= 1.0 or percent >= 100:
                self.last_text_update = now
                update_text = True
                if total and downloaded and avg_speed > 0:
                    remaining = total - downloaded
                    eta_secs = remaining / avg_speed
                    eta_str = self.format_eta(eta_secs)
                else:
                    eta_str = "--:--"

                speed_str = self.format_speed(avg_speed)
                percent_str = f"{int(percent)}%"
                text_to_show = f"{percent_str} • {speed_str} • ETA {eta_str}"

            self.progress_signal.emit({
                "status": "downloading",
                "percent": percent,
                "update_text": update_text,
                "text": text_to_show
            })

        elif status == "processing":
            self.progress_signal.emit({
                "status": "processing",
                "action": raw_dados.get("action", "Processando mídia...")
            })


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("VideoDownloaderApp", "VideoDownloader")
        self.setWindowTitle(f"VideoDownloader v{__version__}")
        self.resize(740, 580)
        self.setMinimumSize(680, 530)
        self.setObjectName("mainWindowWidget")

        # Configuração do tema (Padrão: Light Mode)
        salvo = self.settings.value("theme", "light")
        self.current_theme = "dark" if salvo == "dark" else "light"

        self.worker = None
        self.update_checker = None
        self.update_downloader = None
        self.progress_dialog = None
        self._is_silent_update = False
        self._closing_pending = False
        self._startup_update_checked = False
        self._pending_update = None

        self.setup_ui()
        self.apply_theme()

        self.last_active_browser = None
        initial_hwnd = ctypes.windll.user32.GetForegroundWindow()
        self.last_active_browser = self._get_browser_from_hwnd(initial_hwnd)
        if not self.last_active_browser:
            self.last_active_browser = get_fallback_browser()

        self._setup_window_hook()

        # Agenda verificação silenciosa inicial após 3 segundos
        QTimer.singleShot(3000, self._verificar_atualizacao_automatica)

    def _verificar_atualizacao_automatica(self):
        if self._closing_pending:
            return
        if self._startup_update_checked:
            return
        if (self.update_checker and self.update_checker.isRunning()) or (
            self.update_downloader and self.update_downloader.isRunning()
        ):
            return

        self._startup_update_checked = True
        self.verificar_atualizacao(silencioso=True)

    def verificar_atualizacao(self, silencioso=False):
        if self._closing_pending:
            return
        if (self.update_checker and self.update_checker.isRunning()) or (
            self.update_downloader and self.update_downloader.isRunning()
        ):
            if not silencioso:
                QMessageBox.information(
                    self,
                    "Atualização",
                    "Uma verificação ou download de atualização já está em andamento."
                )
            return

        self._is_silent_update = silencioso
        self.update_checker = UpdateChecker(self)
        self.update_checker.update_available.connect(self._on_update_available)
        self.update_checker.no_update.connect(self._on_no_update)
        self.update_checker.error.connect(self._on_update_error)
        self.update_checker.start()

    def _on_update_available(self, version, notes, installer_url, checksum_url, api_sha256):
        if self._closing_pending:
            return

        if self.worker and self.worker.isRunning():
            self._pending_update = (version, notes, installer_url, checksum_url, api_sha256)
            return

        self._pending_update = None
        self._exibir_janela_atualizacao(version, notes, installer_url, checksum_url, api_sha256)

    def _exibir_janela_atualizacao(self, version, notes, installer_url, checksum_url, api_sha256):
        if self._closing_pending:
            return

        clean_remote_ver = version.lstrip("vV")
        clean_local_ver = __version__.lstrip("vV")
        summary = format_release_notes(notes, owner=GITHUB_OWNER, repo=GITHUB_REPO)

        msg = QMessageBox(self)
        msg.setWindowTitle("Nova versão disponível")
        msg.setIcon(QMessageBox.Information)
        msg.setTextFormat(Qt.PlainText)
        msg.setText(
            "Uma nova versão do VideoDownloader está disponível!\n\n"
            f"Versão atual: {clean_local_ver}\n"
            f"Nova versão: {clean_remote_ver}\n\n"
            f"O que mudou:\n{summary}\n\n"
            "Deseja atualizar agora?"
        )

        btn_atualizar = msg.addButton("Baixar e instalar", QMessageBox.AcceptRole)
        btn_depois = msg.addButton("Lembrar mais tarde", QMessageBox.RejectRole)
        msg.setDefaultButton(btn_atualizar)

        msg.exec()

        if msg.clickedButton() == btn_atualizar:
            self._iniciar_download_atualizacao(installer_url, checksum_url, api_sha256)

    def _on_no_update(self):
        if not self._is_silent_update and not self._closing_pending:
            QMessageBox.information(
                self,
                "Atualização",
                f"Você já está utilizando a versão mais recente (v{__version__})."
            )

    def _on_update_error(self, err_msg):
        if self._closing_pending:
            return
        if not self._is_silent_update:
            QMessageBox.warning(self, "Verificação de atualização", err_msg)
        else:
            print(f"[Atualizador] Verificação silenciosa na inicialização ignorada: {err_msg}")

    def _iniciar_download_atualizacao(self, installer_url, checksum_url, api_sha256):
        temp_dir = tempfile.gettempdir()
        self.progress_dialog = QProgressDialog("Baixando instalador da atualização...", "Cancelar", 0, 100, self)
        self.progress_dialog.setWindowTitle("Atualizando VideoDownloader")
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.setAutoClose(False)
        self.progress_dialog.setAutoReset(False)
        self.progress_dialog.setValue(0)

        self.update_downloader = UpdateDownloader(
            installer_url,
            checksum_url,
            temp_dir,
            expected_digest=api_sha256,
            parent=self
        )
        self.update_downloader.progress.connect(self._on_update_download_progress)
        self.update_downloader.finished_download.connect(self._executar_instalador)
        self.update_downloader.error.connect(self._on_download_update_error)
        self.progress_dialog.canceled.connect(self.update_downloader.cancel)

        self.update_downloader.start()
        self.progress_dialog.show()

    def _on_update_download_progress(self, val):
        if not self.progress_dialog:
            return
        if val == 0 and self.progress_dialog.maximum() != 0:
            self.progress_dialog.setRange(0, 0)
        elif val > 0:
            if self.progress_dialog.maximum() == 0:
                self.progress_dialog.setRange(0, 100)
            self.progress_dialog.setValue(val)

    def _fechar_progress_dialog(self):
        if self.progress_dialog:
            try:
                self.progress_dialog.canceled.disconnect()
            except Exception:
                pass
            self.progress_dialog.close()
            self.progress_dialog = None

    def _on_download_update_error(self, err_msg):
        self._fechar_progress_dialog()
        if not self._closing_pending:
            QMessageBox.warning(self, "Atualização não concluída", err_msg)

    def _executar_instalador(self, installer_path):
        self._fechar_progress_dialog()
        if self._closing_pending:
            return

        try:
            os.startfile(installer_path)
            self.close()
        except Exception as e:
            QMessageBox.critical(
                self,
                "Erro ao iniciar instalador",
                f"Não foi possível iniciar o instalador da atualização:\n{e}"
            )

    def _setup_window_hook(self):
        self._win_event_proc = WINEVENTPROC(self._on_foreground_change)
        self._hook_id = ctypes.windll.user32.SetWinEventHook(
            EVENT_SYSTEM_FOREGROUND,
            EVENT_SYSTEM_FOREGROUND,
            0,
            self._win_event_proc,
            0,
            0,
            WINEVENT_OUTOFCONTEXT
        )

    def _on_foreground_change(self, hWinEventHook, event, hwnd, idObject, idChild, dwEventThread, dwmsEventTime):
        if event == EVENT_SYSTEM_FOREGROUND and hwnd:
            browser = self._get_browser_from_hwnd(hwnd)
            if browser and browser != self.last_active_browser:
                self.last_active_browser = browser

    def _get_browser_from_hwnd(self, hwnd):
        browser_map = {
            "chrome.exe": "chrome",
            "msedge.exe": "edge",
            "firefox.exe": "firefox",
            "brave.exe": "brave",
            "opera.exe": "opera",
            "vivaldi.exe": "vivaldi"
        }
        try:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            process_handle = kernel32.OpenProcess(0x1000, False, pid.value)
            if process_handle:
                buffer = ctypes.create_unicode_buffer(260)
                size = ctypes.c_ulong(260)
                success = kernel32.QueryFullProcessImageNameW(process_handle, 0, buffer, ctypes.byref(size))
                kernel32.CloseHandle(process_handle)
                if success:
                    exe_name = os.path.basename(buffer.value).lower()
                    if exe_name in browser_map:
                        return browser_map[exe_name]
        except Exception:
            pass
        return None

    def _threads_ativas(self):
        ativas = []
        if self.worker and self.worker.isRunning():
            ativas.append(self.worker)
        if self.update_checker and self.update_checker.isRunning():
            ativas.append(self.update_checker)
        if self.update_downloader and self.update_downloader.isRunning():
            ativas.append(self.update_downloader)
        return ativas

    def closeEvent(self, event: QCloseEvent):
        self._closing_pending = True
        self._fechar_progress_dialog()

        if self.worker and self.worker.isRunning():
            self.worker.cancelar()
        if self.update_checker and self.update_checker.isRunning():
            self.update_checker.cancel()
        if self.update_downloader and self.update_downloader.isRunning():
            self.update_downloader.cancel()

        for t in self._threads_ativas():
            t.wait(150)

        restantes = self._threads_ativas()
        if restantes:
            event.ignore()
            self.setEnabled(False)
            self.aplicar_status("● Encerrando operações em segundo plano...", "aviso")
            for t in restantes:
                try:
                    t.finished.connect(self.close, Qt.UniqueConnection)
                except Exception:
                    pass
            return

        if hasattr(self, "_hook_id") and self._hook_id:
            ctypes.windll.user32.UnhookWinEvent(self._hook_id)
            self._hook_id = 0

        super().closeEvent(event)

    def _popular_formatos(self):
        model = QStandardItemModel()
        palette = get_theme_palette(self.current_theme)
        doc_icon = get_document_icon(palette["accent_blue"], 16)

        def add_header(titulo):
            item = QStandardItem(titulo)
            item.setFlags(Qt.NoItemFlags)
            font = QFont()
            font.setBold(True)
            item.setFont(font)
            model.appendRow(item)

        def add_option(label, valor):
            item = QStandardItem(f" {label}")
            item.setData(valor, Qt.UserRole)
            item.setIcon(doc_icon)
            model.appendRow(item)

        add_header("── Formatos de Vídeo ──")
        for fmt in ["MP4", "MKV", "WebM", "MOV", "AVI"]:
            add_option(f"{fmt} (Vídeo)", fmt.lower())

        add_header("── Formatos de Áudio ──")
        for fmt in ["MP3", "M4A", "WAV", "FLAC", "Opus"]:
            add_option(f"{fmt} (Somente Áudio)", fmt.lower())

        self.combo_formato.setModel(model)
        formato_salvo = str(self.settings.value("output_format", "mp4")).lower()
        idx_encontrado = -1
        for i in range(model.rowCount()):
            if model.item(i).data(Qt.UserRole) == formato_salvo:
                idx_encontrado = i
                break

        if idx_encontrado != -1:
            self.combo_formato.setCurrentIndex(idx_encontrado)
        else:
            self.combo_formato.setCurrentIndex(1)
        self.combo_formato.currentIndexChanged.connect(self._salvar_formato_escolhido)

    def _salvar_formato_escolhido(self):
        formato_atual = self.combo_formato.currentData(Qt.UserRole)
        if formato_atual:
            self.settings.setValue("output_format", formato_atual)

    def setup_ui(self):
        # Layout raiz horizontal: Barra Lateral (esquerda) + Área de Conteúdo (direita)
        root_layout = QHBoxLayout()
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # -------------------------------------------------------------
        # 1. BARRA LATERAL VERTICAL (ESQUERDA)
        # -------------------------------------------------------------
        self.sidebar_widget = QWidget()
        self.sidebar_widget.setObjectName("sidebarContainer")
        self.sidebar_widget.setFixedWidth(68)

        sidebar_layout = QVBoxLayout(self.sidebar_widget)
        sidebar_layout.setContentsMargins(12, 16, 12, 16)
        sidebar_layout.setSpacing(12)
        sidebar_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        self.btn_nav_home = SidebarNavButton(0, "home", "Início", self)
        self.btn_nav_settings = SidebarNavButton(1, "settings", "Configurações", self)
        self.btn_nav_info = SidebarNavButton(2, "info", "Informações", self)

        self.btn_nav_home.clicked.connect(lambda: self._navegar_para(0))
        self.btn_nav_settings.clicked.connect(lambda: self._navegar_para(1))
        self.btn_nav_info.clicked.connect(lambda: self._navegar_para(2))

        sidebar_layout.addWidget(self.btn_nav_home)
        sidebar_layout.addWidget(self.btn_nav_settings)
        sidebar_layout.addWidget(self.btn_nav_info)
        sidebar_layout.addStretch()

        root_layout.addWidget(self.sidebar_widget)

        # -------------------------------------------------------------
        # 2. ÁREA DE CONTEÚDO COM FUNDO DE ONDA (DIREITA)
        # -------------------------------------------------------------
        self.bg_content_widget = ContentBackgroundWidget(self.current_theme, self)
        content_main_layout = QVBoxLayout(self.bg_content_widget)
        content_main_layout.setContentsMargins(28, 20, 28, 20)
        content_main_layout.setSpacing(16)

        # Cabeçalho Principal (Logo, Título, Subtítulo e Theme Toggle)
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(14)

        # Ícone do aplicativo em destaque
        self.lbl_app_logo = QLabel()
        self.lbl_app_logo.setFixedSize(52, 52)
        self.lbl_app_logo.setPixmap(get_app_icon_pixmap(52))
        header_layout.addWidget(self.lbl_app_logo)

        # Título e Subtítulo
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        self.lbl_titulo = QLabel("VideoDownloader")
        self.lbl_titulo.setObjectName("headerTitle")
        self.lbl_subtitulo = QLabel("Baixe seus vídeos de forma simples")
        self.lbl_subtitulo.setObjectName("headerSubtitle")
        title_box.addWidget(self.lbl_titulo)
        title_box.addWidget(self.lbl_subtitulo)
        header_layout.addLayout(title_box)

        header_layout.addStretch()

        # Controle de alternância Light / Dark Mode
        self.theme_toggle = ThemeToggleWidget(self.current_theme, self)
        self.theme_toggle.theme_toggled.connect(self.set_theme)
        header_layout.addWidget(self.theme_toggle, 0, Qt.AlignVCenter)

        content_main_layout.addLayout(header_layout)

        # QStackedWidget para as 3 páginas da navegação
        self.stack = QStackedWidget()
        self.stack.addWidget(self._criar_pagina_home())
        self.stack.addWidget(self._criar_pagina_configuracoes())
        self.stack.addWidget(self._criar_pagina_informacoes())

        content_main_layout.addWidget(self.stack, 1)

        root_layout.addWidget(self.bg_content_widget, 1)
        self.setLayout(root_layout)

        # Preserva referência oculta ao QMenuBar para total retrocompatibilidade de testes
        self.menu_bar = QMenuBar(self)
        self.menu_bar.hide()

        # Ativa a visualização da página inicial
        self._navegar_para(0)

    def _criar_pagina_home(self) -> QWidget:
        """Página principal de download, reproduzindo exatamente o layout da imagem de referência."""
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 4, 0, 0)
        page_layout.setSpacing(0)

        # Cartão principal com cantos arredondados e borda sutil
        self.main_card = QFrame()
        self.main_card.setObjectName("mainCard")
        card_layout = QVBoxLayout(self.main_card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(14)

        # 1. Rótulo e Campo de URL em destaque
        lbl_url = QLabel("URL do vídeo")
        lbl_url.setObjectName("fieldLabel")
        card_layout.addWidget(lbl_url)

        self.input_url = QLineEdit()
        self.input_url.setObjectName("urlInput")
        self.input_url.setPlaceholderText("Cole aqui o link do vídeo...")
        palette = get_theme_palette(self.current_theme)
        self.action_link_icon = self.input_url.addAction(
            get_link_icon(palette["text_muted"], 18),
            QLineEdit.LeadingPosition
        )
        card_layout.addWidget(self.input_url)

        # 2. Linha horizontal com os dois subcartões (Pasta de destino e Formato de saída)
        middle_row = QHBoxLayout()
        middle_row.setSpacing(14)

        # Subcartão: Pasta de destino
        subcard_pasta = QFrame()
        subcard_pasta.setObjectName("subCard")
        subcard_pasta_layout = QVBoxLayout(subcard_pasta)
        subcard_pasta_layout.setContentsMargins(14, 12, 14, 12)
        subcard_pasta_layout.setSpacing(8)

        lbl_pasta_header = QHBoxLayout()
        lbl_pasta_header.setSpacing(6)
        self.lbl_pasta_icon = QLabel()
        self.lbl_pasta_icon.setFixedSize(16, 16)
        self.lbl_pasta_icon.setPixmap(get_folder_pixmap(palette["text_secondary"], 16))
        lbl_pasta = QLabel("Pasta de destino")
        lbl_pasta.setObjectName("subCardLabel")
        lbl_pasta_header.addWidget(self.lbl_pasta_icon)
        lbl_pasta_header.addWidget(lbl_pasta)
        lbl_pasta_header.addStretch()
        subcard_pasta_layout.addLayout(lbl_pasta_header)

        pasta_input_row = QHBoxLayout()
        pasta_input_row.setSpacing(8)

        self.input_pasta = QLineEdit()
        self.input_pasta.setObjectName("folderInput")
        pasta_salva = self.settings.value("download_folder", "")
        pasta_padrao = pathlib.Path.home() / "Downloads" / "VideoDownloader"
        if pasta_salva and pathlib.Path(pasta_salva).exists():
            self.input_pasta.setText(pasta_salva)
        else:
            self.input_pasta.setText(str(pasta_padrao))

        self.btn_escolher = QPushButton()
        self.btn_escolher.setObjectName("btnBrowse")
        self.btn_escolher.setCursor(Qt.PointingHandCursor)
        self.btn_escolher.setFixedSize(36, 32)
        self.btn_escolher.setIcon(get_folder_icon(palette["accent_blue"], 18))
        self.btn_escolher.setToolTip("Selecionar pasta de destino")
        self.btn_escolher.clicked.connect(self.escolher_pasta)

        pasta_input_row.addWidget(self.input_pasta, 1)
        pasta_input_row.addWidget(self.btn_escolher)
        subcard_pasta_layout.addLayout(pasta_input_row)
        middle_row.addWidget(subcard_pasta, 1)

        # Subcartão: Formato de saída
        subcard_formato = QFrame()
        subcard_formato.setObjectName("subCard")
        subcard_formato_layout = QVBoxLayout(subcard_formato)
        subcard_formato_layout.setContentsMargins(14, 12, 14, 12)
        subcard_formato_layout.setSpacing(8)

        lbl_formato_header = QHBoxLayout()
        lbl_formato_header.setSpacing(6)
        self.lbl_formato_icon = QLabel()
        self.lbl_formato_icon.setFixedSize(16, 16)
        self.lbl_formato_icon.setPixmap(get_document_pixmap(palette["text_secondary"], 16))
        lbl_formato = QLabel("Formato de saída")
        lbl_formato.setObjectName("subCardLabel")
        lbl_formato_header.addWidget(self.lbl_formato_icon)
        lbl_formato_header.addWidget(lbl_formato)
        lbl_formato_header.addStretch()
        subcard_formato_layout.addLayout(lbl_formato_header)

        self.combo_formato = QComboBox()
        self.combo_formato.setObjectName("formatCombo")
        self.combo_formato.setCursor(Qt.PointingHandCursor)
        self._popular_formatos()

        subcard_formato_layout.addWidget(self.combo_formato)
        middle_row.addWidget(subcard_formato, 1)

        card_layout.addLayout(middle_row)
        card_layout.addSpacing(6)

        # 3. Botão Principal BAIXAR em azul ocupando toda a largura
        self.btn_baixar = QPushButton("Baixar")
        self.btn_baixar.setObjectName("primaryButton")
        self.btn_baixar.setCursor(Qt.PointingHandCursor)
        self.btn_baixar.setFixedHeight(44)
        self.btn_baixar.setIcon(get_download_button_icon("white", 18))
        self.btn_baixar.clicked.connect(self.acao_botao_principal)
        card_layout.addWidget(self.btn_baixar)

        card_layout.addSpacing(8)

        # 4. Área inferior: Status com indicador circular, barra de progresso e percentual
        status_row = QHBoxLayout()
        status_row.setSpacing(12)

        self.lbl_status = QLabel("● Pronto para baixar")
        self.lbl_status.setObjectName("statusLabel")
        status_row.addWidget(self.lbl_status)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("progressBar")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(8)
        status_row.addWidget(self.progress_bar, 1)

        self.lbl_percent = QLabel("0%")
        self.lbl_percent.setObjectName("percentLabel")
        status_row.addWidget(self.lbl_percent)

        card_layout.addLayout(status_row)

        # Linha oculta para dados detalhados (velocidade / ETA) durante downloads
        self.lbl_stats = QLabel("")
        self.lbl_stats.setObjectName("statsLabel")
        self.lbl_stats.hide()
        card_layout.addWidget(self.lbl_stats)

        page_layout.addWidget(self.main_card)
        page_layout.addStretch()
        return page

    def _criar_pagina_configuracoes(self) -> QWidget:
        """Página funcional de preferências e configurações com layout limpo e adaptável."""
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 4, 0, 0)
        page_layout.setSpacing(0)

        card = QFrame()
        card.setObjectName("mainCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(12)

        # Cabeçalho da página
        lbl_title = QLabel("Configurações")
        lbl_title.setObjectName("pageTitle")
        lbl_subtitle = QLabel("Personalize as preferências de aparência, download e autenticação.")
        lbl_subtitle.setObjectName("pageSubtitle")
        layout.addWidget(lbl_title)
        layout.addWidget(lbl_subtitle)

        # Seção 1: Aparência e Tema
        sec_tema = QFrame()
        sec_tema.setObjectName("subCard")
        sec_tema_layout = QHBoxLayout(sec_tema)
        sec_tema_layout.setContentsMargins(16, 12, 16, 12)
        sec_tema_layout.setSpacing(12)

        tema_info = QVBoxLayout()
        tema_info.setSpacing(2)
        lbl_t_title = QLabel("Tema do aplicativo")
        lbl_t_title.setObjectName("settingSectionTitle")
        lbl_t_desc = QLabel("Alterne entre os modos Claro e Escuro.")
        lbl_t_desc.setObjectName("settingSectionDesc")
        tema_info.addWidget(lbl_t_title)
        tema_info.addWidget(lbl_t_desc)
        sec_tema_layout.addLayout(tema_info, 1)

        tema_btn_row = QHBoxLayout()
        tema_btn_row.setSpacing(8)
        self.btn_tema_claro = QPushButton("☀️ Modo Claro")
        self.btn_tema_claro.setObjectName("secondaryActionButton")
        self.btn_tema_claro.setCursor(Qt.PointingHandCursor)
        self.btn_tema_claro.clicked.connect(lambda: self.set_theme("light"))

        self.btn_tema_escuro = QPushButton("🌙 Modo Escuro")
        self.btn_tema_escuro.setObjectName("secondaryActionButton")
        self.btn_tema_escuro.setCursor(Qt.PointingHandCursor)
        self.btn_tema_escuro.clicked.connect(lambda: self.set_theme("dark"))

        tema_btn_row.addWidget(self.btn_tema_claro)
        tema_btn_row.addWidget(self.btn_tema_escuro)
        sec_tema_layout.addLayout(tema_btn_row)
        layout.addWidget(sec_tema)

        # Seção 2: Cookies e Navegador
        sec_cookies = QFrame()
        sec_cookies.setObjectName("subCard")
        sec_cookies_layout = QHBoxLayout(sec_cookies)
        sec_cookies_layout.setContentsMargins(16, 12, 16, 12)
        sec_cookies_layout.setSpacing(12)

        cookie_info = QVBoxLayout()
        cookie_info.setSpacing(2)
        lbl_c_title = QLabel("Navegador para cookies")
        lbl_c_title.setObjectName("settingSectionTitle")
        lbl_c_desc = QLabel("Sessão utilizada para baixar mídias restritas.")
        lbl_c_desc.setObjectName("settingSectionDesc")
        cookie_info.addWidget(lbl_c_title)
        cookie_info.addWidget(lbl_c_desc)
        sec_cookies_layout.addLayout(cookie_info, 1)

        self.combo_browser = QComboBox()
        self.combo_browser.setObjectName("formatCombo")
        self.combo_browser.setMinimumWidth(230)
        browsers = [
            ("Automático (Navegador ativo)", "auto"),
            ("Google Chrome", "chrome"),
            ("Microsoft Edge", "edge"),
            ("Mozilla Firefox", "firefox"),
            ("Brave", "brave"),
            ("Opera", "opera"),
            ("Vivaldi", "vivaldi")
        ]
        for label, val in browsers:
            self.combo_browser.addItem(label, val)

        salvo_b = self.settings.value("preferred_browser", "auto")
        for i in range(self.combo_browser.count()):
            if self.combo_browser.itemData(i) == salvo_b:
                self.combo_browser.setCurrentIndex(i)
                break
        self.combo_browser.currentIndexChanged.connect(self._salvar_navegador_preferido)

        sec_cookies_layout.addWidget(self.combo_browser)
        layout.addWidget(sec_cookies)

        # Seção 3: Atualizações
        sec_updates = QFrame()
        sec_updates.setObjectName("subCard")
        sec_updates_layout = QHBoxLayout(sec_updates)
        sec_updates_layout.setContentsMargins(16, 12, 16, 12)
        sec_updates_layout.setSpacing(12)

        update_info = QVBoxLayout()
        update_info.setSpacing(2)
        lbl_u_title = QLabel("Atualizações do sistema")
        lbl_u_title.setObjectName("settingSectionTitle")
        lbl_u_desc = QLabel("Verificação automática ativa a cada inicialização.")
        lbl_u_desc.setObjectName("settingSectionDesc")
        update_info.addWidget(lbl_u_title)
        update_info.addWidget(lbl_u_desc)
        sec_updates_layout.addLayout(update_info, 1)

        btn_verificar = QPushButton("Verificar agora")
        btn_verificar.setObjectName("secondaryActionButton")
        btn_verificar.setCursor(Qt.PointingHandCursor)
        btn_verificar.clicked.connect(lambda: self.verificar_atualizacao(silencioso=False))
        sec_updates_layout.addWidget(btn_verificar)

        layout.addWidget(sec_updates)
        layout.addStretch()

        page_layout.addWidget(card)
        return page

    def _salvar_navegador_preferido(self):
        val = self.combo_browser.currentData()
        if val:
            self.settings.setValue("preferred_browser", val)
            if val != "auto":
                self.last_active_browser = val

    def _criar_pagina_informacoes(self) -> QWidget:
        """Página de informações sobre o aplicativo, valorizando versão, créditos e GitHub."""
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 4, 0, 0)
        page_layout.setSpacing(0)

        card = QFrame()
        card.setObjectName("mainCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(14)

        # 1. Cabeçalho com Logo, Título e Versão em destaque
        header_card = QFrame()
        header_card.setObjectName("subCard")
        header_card_layout = QHBoxLayout(header_card)
        header_card_layout.setContentsMargins(16, 14, 16, 14)
        header_card_layout.setSpacing(14)

        lbl_logo = QLabel()
        lbl_logo.setFixedSize(48, 48)
        lbl_logo.setPixmap(get_app_icon_pixmap(48))
        header_card_layout.addWidget(lbl_logo)

        info_title_box = QVBoxLayout()
        info_title_box.setSpacing(2)
        lbl_app_name = QLabel("VideoDownloader")
        lbl_app_name.setObjectName("pageTitle")
        lbl_app_desc = QLabel("Baixe vídeos e áudios de múltiplos serviços com máxima facilidade.")
        lbl_app_desc.setObjectName("pageSubtitle")
        info_title_box.addWidget(lbl_app_name)
        info_title_box.addWidget(lbl_app_desc)
        header_card_layout.addLayout(info_title_box, 1)

        badge_ver = QLabel(f"Versão {__version__}")
        badge_ver.setObjectName("versionBadge")
        badge_ver.setToolTip("Versão instalada do VideoDownloader")
        header_card_layout.addWidget(badge_ver)

        layout.addWidget(header_card)

        # 2. Créditos essenciais (foco no que importa, sem excesso técnico)
        sec_tech = QFrame()
        sec_tech.setObjectName("subCard")
        sec_tech_layout = QVBoxLayout(sec_tech)
        sec_tech_layout.setContentsMargins(16, 14, 16, 14)
        sec_tech_layout.setSpacing(8)

        lbl_tech_title = QLabel("Créditos e Ferramentas Integradas")
        lbl_tech_title.setObjectName("settingSectionTitle")
        sec_tech_layout.addWidget(lbl_tech_title)

        techs = [
            ("yt-dlp", "Mecanismo open-source para extração e download de mídias de alta fidelidade."),
            ("FFmpeg", "Processamento, conversão e mesclagem de áudio e vídeo embutidos.")
        ]
        for name, desc in techs:
            row = QHBoxLayout()
            row.setSpacing(8)
            lbl_name = QLabel(f"• <b>{name}</b>:")
            lbl_name.setTextFormat(Qt.RichText)
            lbl_desc = QLabel(desc)
            lbl_desc.setObjectName("settingSectionDesc")
            row.addWidget(lbl_name)
            row.addWidget(lbl_desc, 1)
            sec_tech_layout.addLayout(row)

        layout.addWidget(sec_tech)

        # 3. Seção do Repositório GitHub e Atualizações em destaque
        sec_links = QFrame()
        sec_links.setObjectName("subCard")
        sec_links_layout = QVBoxLayout(sec_links)
        sec_links_layout.setContentsMargins(16, 12, 16, 12)
        sec_links_layout.setSpacing(8)

        lbl_l_title = QLabel("Projeto & Atualizações no GitHub")
        lbl_l_title.setObjectName("settingSectionTitle")
        lbl_l_desc = QLabel("Código-fonte oficial, notas de versão e links de suporte.")
        lbl_l_desc.setObjectName("settingSectionDesc")
        sec_links_layout.addWidget(lbl_l_title)
        sec_links_layout.addWidget(lbl_l_desc)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        btn_repo = QPushButton("⭐ Repositório no GitHub")
        btn_repo.setObjectName("secondaryActionButton")
        btn_repo.setCursor(Qt.PointingHandCursor)
        btn_repo.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}")))

        btn_check = QPushButton("🔄 Verificar atualizações")
        btn_check.setObjectName("secondaryActionButton")
        btn_check.setCursor(Qt.PointingHandCursor)
        btn_check.clicked.connect(lambda: self.verificar_atualizacao(silencioso=False))

        btn_row.addWidget(btn_repo)
        btn_row.addWidget(btn_check)
        btn_row.addStretch()

        sec_links_layout.addLayout(btn_row)
        layout.addWidget(sec_links)
        layout.addStretch()

        page_layout.addWidget(card)
        return page

        page_layout.addWidget(card)
        return page

    def _navegar_para(self, index: int):
        self.stack.setCurrentIndex(index)
        self.btn_nav_home.set_theme_and_active(self.current_theme, index == 0)
        self.btn_nav_settings.set_theme_and_active(self.current_theme, index == 1)
        self.btn_nav_info.set_theme_and_active(self.current_theme, index == 2)

    def set_theme(self, theme_name: str):
        if theme_name not in ("light", "dark"):
            theme_name = "light"
        self.current_theme = theme_name
        self.settings.setValue("theme", theme_name)
        self.apply_theme()

    def apply_theme(self):
        # 1. Aplica o Stylesheet QSS completo
        self.setStyleSheet(get_theme_stylesheet(self.current_theme))

        # 2. Atualiza a onda decorativa de fundo
        if hasattr(self, "bg_content_widget"):
            self.bg_content_widget.set_theme(self.current_theme)

        # 3. Atualiza o controle ThemeToggle
        if hasattr(self, "theme_toggle"):
            self.theme_toggle.set_theme(self.current_theme)

        # 4. Atualiza os botões da barra lateral
        current_idx = self.stack.currentIndex() if hasattr(self, "stack") else 0
        if hasattr(self, "btn_nav_home"):
            self.btn_nav_home.set_theme_and_active(self.current_theme, current_idx == 0)
        if hasattr(self, "btn_nav_settings"):
            self.btn_nav_settings.set_theme_and_active(self.current_theme, current_idx == 1)
        if hasattr(self, "btn_nav_info"):
            self.btn_nav_info.set_theme_and_active(self.current_theme, current_idx == 2)

        # 5. Atualiza ícones dos botões e campos
        palette = get_theme_palette(self.current_theme)
        if hasattr(self, "lbl_pasta_icon"):
            self.lbl_pasta_icon.setPixmap(get_folder_pixmap(palette["text_secondary"], 16))
        if hasattr(self, "lbl_formato_icon"):
            self.lbl_formato_icon.setPixmap(get_document_pixmap(palette["text_secondary"], 16))
        if hasattr(self, "btn_escolher"):
            self.btn_escolher.setIcon(get_folder_icon(palette["accent_blue"], 18))
        if hasattr(self, "action_link_icon"):
            self.action_link_icon.setIcon(get_link_icon(palette["text_muted"], 18))
        if hasattr(self, "btn_baixar") and "BAIXAR" in self.btn_baixar.text().upper():
            self.btn_baixar.setIcon(get_download_button_icon("white", 18))
        if hasattr(self, "btn_tema_claro"):
            self.btn_tema_claro.setProperty("active", "true" if self.current_theme == "light" else "false")
            self.btn_tema_claro.style().unpolish(self.btn_tema_claro)
            self.btn_tema_claro.style().polish(self.btn_tema_claro)
        if hasattr(self, "btn_tema_escuro"):
            self.btn_tema_escuro.setProperty("active", "true" if self.current_theme == "dark" else "false")
            self.btn_tema_escuro.style().unpolish(self.btn_tema_escuro)
            self.btn_tema_escuro.style().polish(self.btn_tema_escuro)

        # 6. Atualiza cores de status
        if hasattr(self, "lbl_status"):
            self.aplicar_status(self.lbl_status.text(), "normal")

    def apply_stylesheet(self):
        """Método de retrocompatibilidade com versões anteriores."""
        self.apply_theme()

    def aplicar_status(self, mensagem, tipo="normal"):
        self.lbl_status.setText(mensagem)
        palette = get_theme_palette(self.current_theme)
        if tipo == "erro":
            color = palette["status_dot_error"]
        elif tipo == "sucesso":
            color = palette["status_dot_success"]
        elif tipo == "aviso":
            color = palette["status_dot_warning"]
        else:
            color = palette["status_dot_normal"]
        self.lbl_status.setStyleSheet(f"color: {color}; font-weight: 500;")

    def escolher_pasta(self):
        pasta_atual = self.input_pasta.text()
        nova_pasta = QFileDialog.getExistingDirectory(self, "Selecione a pasta", pasta_atual)
        if nova_pasta:
            self.input_pasta.setText(nova_pasta)
            self.settings.setValue("download_folder", nova_pasta)

    def acao_botao_principal(self):
        if "BAIXAR" in self.btn_baixar.text().upper():
            self.iniciar_download()
        else:
            self.cancelar_download()

    def cancelar_download(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancelar()
            self.btn_baixar.setEnabled(False)
            self.btn_baixar.setText("CANCELANDO...")
            self.aplicar_status("● Cancelando download. Aguarde...", "aviso")

    def iniciar_download(self):
        url = self.input_url.text().strip()
        pasta = self.input_pasta.text().strip()
        formato = self.combo_formato.currentData(Qt.UserRole) or "mp4"

        if not url:
            self.aplicar_status("● Erro: A URL não pode estar vazia.", "erro")
            return
        if not pasta:
            self.aplicar_status("● Erro: A pasta não pode estar vazia.", "erro")
            return

        self.settings.setValue("download_folder", pasta)
        self.settings.setValue("output_format", formato)

        self.combo_formato.setEnabled(False)
        self.btn_escolher.setEnabled(False)
        self.btn_baixar.setText("CANCELAR")
        self.btn_baixar.setIcon(QIcon())
        palette = get_theme_palette(self.current_theme)
        self.btn_baixar.setStyleSheet(f"""
            QPushButton {{
                background-color: {palette["button_cancel"]};
                color: white;
                border-radius: 8px;
                padding: 12px 24px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {palette["button_cancel_hover"]};
            }}
        """)

        self.aplicar_status("● Iniciando requisição...", "normal")
        self.progress_bar.setRange(0, 0)
        self.lbl_percent.setText("0%")
        self.lbl_stats.hide()

        # Determina navegador ativo de acordo com as preferências do usuário
        browser_pref = self.settings.value("preferred_browser", "auto")
        chosen_browser = self.last_active_browser if browser_pref == "auto" else browser_pref

        self.worker = DownloadWorker(url, pasta, output_format=formato, active_browser=chosen_browser)
        self.worker.progress_signal.connect(self.atualizar_progresso)
        self.worker.finished_signal.connect(self.finalizar_download)
        self.worker.start()

    def atualizar_progresso(self, dados):
        status = dados.get("status")
        if status == "extracting":
            self.aplicar_status("● Analisando o link...", "normal")
            self.lbl_stats.setText("Descobrindo informações da página...")
            self.lbl_stats.show()
            self.progress_bar.setRange(0, 0)
        elif status == "downloading":
            self.aplicar_status("● Baixando...", "normal")
            self.progress_bar.setRange(0, 100)
            percent_val = int(dados["percent"])
            self.progress_bar.setValue(percent_val)
            self.lbl_percent.setText(f"{percent_val}%")
            if dados.get("update_text"):
                self.lbl_stats.setText(dados["text"])
                self.lbl_stats.show()
        elif status == "processing":
            acao = dados.get("action", "Mesclando e convertendo mídia...")
            self.aplicar_status("● Processando arquivo final (pode levar alguns instantes)...", "normal")
            self.lbl_stats.setText(acao)
            self.lbl_stats.show()
            self.progress_bar.setRange(0, 0)

    def finalizar_download(self, status, mensagem):
        self.btn_baixar.setText("Baixar")
        self.btn_baixar.setStyleSheet("")
        self.btn_baixar.setIcon(get_download_button_icon("white", 18))
        self.btn_baixar.setEnabled(True)
        self.combo_formato.setEnabled(True)
        self.btn_escolher.setEnabled(True)
        self.progress_bar.setRange(0, 100)

        if status == "sucesso":
            self.aplicar_status("● Download concluído com sucesso!", "sucesso")
            self.progress_bar.setValue(100)
            self.lbl_percent.setText("100%")
            self.lbl_stats.setText("Processo finalizado.")
            self.input_url.clear()
        elif status == "cancelado":
            self.aplicar_status("● Download cancelado.", "aviso")
            self.progress_bar.setValue(0)
            self.lbl_percent.setText("0%")
            self.lbl_stats.hide()
        else:
            self.aplicar_status(f"● Erro: {mensagem}", "erro")
            self.progress_bar.setValue(0)
            self.lbl_percent.setText("0%")
            self.lbl_stats.hide()

        # Se houver atualização pendente detectada durante o download de mídia, apresenta agora
        if self._pending_update and not self._closing_pending:
            update_data = self._pending_update
            self._pending_update = None
            self._exibir_janela_atualizacao(*update_data)
