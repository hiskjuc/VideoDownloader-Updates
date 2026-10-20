import pathlib
import time
import os
import ctypes
from ctypes import wintypes
from collections import deque
import tempfile

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QProgressBar, QComboBox,
    QMenuBar, QMessageBox, QProgressDialog
)
from PySide6.QtCore import QThread, Signal, Qt, QSettings, QTimer
from PySide6.QtGui import QCloseEvent, QStandardItemModel, QStandardItem, QFont, QAction

from downloader import download_video, get_fallback_browser
from version import __version__
from updater import UpdateChecker, UpdateDownloader

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
        status, mensagem = download_video(
            self.url,
            self.dest_folder,
            output_format=self.output_format,
            progress_callback=self.enviar_progresso,
            is_cancelled=self.checar_cancelamento,
            active_browser=self.active_browser
        )
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
        self.resize(550, 580)

        self.worker = None
        self.update_checker = None
        self.update_downloader = None
        self.progress_dialog = None
        self._is_silent_update = False
        self._closing_pending = False

        self.setup_ui()
        self.apply_stylesheet()

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
        # Não interrompe downloads de mídia em andamento
        if self.worker and self.worker.isRunning():
            return

        last_check = self.settings.value("last_update_check", 0.0, type=float)
        now = time.time()
        # 86400 segundos = 24 horas
        if (now - last_check) >= 86400:
            self.verificar_atualizacao(silencioso=True)

    def verificar_atualizacao(self, silencioso=False):
        if self._closing_pending:
            return
        if (self.update_checker and self.update_checker.isRunning()) or (
            self.update_downloader and self.update_downloader.isRunning()
        ):
            if not silencioso:
                QMessageBox.information(self, "Atualização", "Uma verificação ou download de atualização já está em andamento.")
            return

        self._is_silent_update = silencioso
        self.update_checker = UpdateChecker(self)
        self.update_checker.update_available.connect(self._on_update_available)
        self.update_checker.no_update.connect(self._on_no_update)
        self.update_checker.error.connect(self._on_update_error)
        self.update_checker.start()

    def _registrar_consulta_concluida(self):
        """Salva o timestamp somente após uma consulta concluída com resposta válida."""
        self.settings.setValue("last_update_check", time.time())

    def _on_update_available(self, version, notes, installer_url, checksum_url, api_sha256):
        self._registrar_consulta_concluida()
        if self._closing_pending:
            return

        # Se um download de vídeo começou enquanto verificava, não interrompe com modal
        if self._is_silent_update and self.worker and self.worker.isRunning():
            return

        msg = QMessageBox(self)
        msg.setWindowTitle("Nova atualização disponível")
        msg.setTextFormat(Qt.PlainText)
        msg.setText(
            f"Uma nova versão do VideoDownloader está disponível!\n\n"
            f"Versão instalada: v{__version__}\n"
            f"Nova versão: {version}\n\n"
            f"Principais alterações:\n{notes}"
        )
        msg.setInformativeText("Deseja baixar e instalar a atualização agora?")
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg.setDefaultButton(QMessageBox.Yes)

        if msg.exec() == QMessageBox.Yes:
            self._iniciar_download_atualizacao(installer_url, checksum_url, api_sha256)

    def _on_no_update(self):
        self._registrar_consulta_concluida()
        if not self._is_silent_update and not self._closing_pending:
            QMessageBox.information(
                self,
                "Atualização",
                f"Você já está utilizando a versão mais recente (v{__version__})."
            )

    def _on_update_error(self, err_msg):
        # Não grava last_update_check em caso de erro para permitir nova tentativa na próxima abertura
        if self._closing_pending:
            return
        if not self._is_silent_update:
            QMessageBox.warning(self, "Verificação de atualização", err_msg)
        else:
            print(f"[Atualizador] Verificação silenciosa ignorada: {err_msg}")

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
            # Modo indeterminado quando Content-Length não é informado
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
                print(f"\n[Fundo] Navegador ativo detectado: {self.last_active_browser.capitalize()}")

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
            # Impede destruição prematura de QThreads que ainda estão saindo de chamadas de rede
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

        def add_header(titulo):
            item = QStandardItem(titulo)
            item.setFlags(Qt.NoItemFlags)
            font = QFont()
            font.setBold(True)
            item.setFont(font)
            model.appendRow(item)

        def add_option(label, valor):
            item = QStandardItem(f"   {label}")
            item.setData(valor, Qt.UserRole)
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
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(30, 30, 30, 30)

        self.menu_bar = QMenuBar(self)
        help_menu = self.menu_bar.addMenu("Ajuda")
        check_update_action = QAction("Verificar atualizações", self)
        check_update_action.triggered.connect(lambda: self.verificar_atualizacao(silencioso=False))
        help_menu.addAction(check_update_action)
        layout.setMenuBar(self.menu_bar)

        self.lbl_titulo = QLabel("VideoDownloader")
        self.lbl_titulo.setObjectName("titleLabel")
        self.lbl_titulo.setAlignment(Qt.AlignCenter)

        self.lbl_subtitulo = QLabel("Baixe seus vídeos de forma simples")
        self.lbl_subtitulo.setObjectName("subtitleLabel")
        self.lbl_subtitulo.setAlignment(Qt.AlignCenter)

        layout.addWidget(self.lbl_titulo)
        layout.addWidget(self.lbl_subtitulo)
        layout.addSpacing(10)

        lbl_url = QLabel("URL do vídeo")
        lbl_url.setObjectName("inputLabel")
        self.input_url = QLineEdit()
        self.input_url.setPlaceholderText("Cole aqui o link do vídeo...")
        layout.addWidget(lbl_url)
        layout.addWidget(self.input_url)

        lbl_pasta = QLabel("Pasta de destino")
        lbl_pasta.setObjectName("inputLabel")
        layout.addWidget(lbl_pasta)

        pasta_layout = QHBoxLayout()
        pasta_layout.setSpacing(10)

        self.input_pasta = QLineEdit()
        pasta_salva = self.settings.value("download_folder", "")
        pasta_padrao = pathlib.Path.home() / "Downloads" / "VideoDownloader"

        if pasta_salva and pathlib.Path(pasta_salva).exists():
            self.input_pasta.setText(pasta_salva)
        else:
            self.input_pasta.setText(str(pasta_padrao))

        self.btn_escolher = QPushButton("...")
        self.btn_escolher.setObjectName("secondaryButton")
        self.btn_escolher.setCursor(Qt.PointingHandCursor)
        self.btn_escolher.setFixedWidth(50)
        self.btn_escolher.clicked.connect(self.escolher_pasta)

        pasta_layout.addWidget(self.input_pasta)
        pasta_layout.addWidget(self.btn_escolher)
        layout.addLayout(pasta_layout)

        lbl_formato = QLabel("Formato de saída")
        lbl_formato.setObjectName("inputLabel")
        layout.addWidget(lbl_formato)

        self.combo_formato = QComboBox()
        self.combo_formato.setCursor(Qt.PointingHandCursor)
        self._popular_formatos()
        layout.addWidget(self.combo_formato)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        self.btn_baixar = QPushButton("BAIXAR")
        self.btn_baixar.setObjectName("primaryButton")
        self.btn_baixar.setCursor(Qt.PointingHandCursor)
        self.btn_baixar.setFixedWidth(200)
        self.btn_baixar.clicked.connect(self.acao_botao_principal)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_baixar)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.lbl_status = QLabel("● Pronto para baixar")
        self.lbl_status.setObjectName("statusLabel")
        layout.addWidget(self.lbl_status)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        self.lbl_stats = QLabel("")
        self.lbl_stats.setObjectName("statsLabel")
        self.lbl_stats.hide()
        layout.addWidget(self.lbl_stats)

        self.setLayout(layout)

    def aplicar_status(self, mensagem, tipo="normal"):
        self.lbl_status.setText(mensagem)
        if tipo == "erro":
            self.lbl_status.setStyleSheet("color: #D32F2F;")
        elif tipo == "sucesso":
            self.lbl_status.setStyleSheet("color: #388E3C;")
        elif tipo == "aviso":
            self.lbl_status.setStyleSheet("color: #E67E22;")
        else:
            self.lbl_status.setStyleSheet("color: #555555;")

    def escolher_pasta(self):
        pasta_atual = self.input_pasta.text()
        nova_pasta = QFileDialog.getExistingDirectory(self, "Selecione a pasta", pasta_atual)
        if nova_pasta:
            self.input_pasta.setText(nova_pasta)
            self.settings.setValue("download_folder", nova_pasta)

    def acao_botao_principal(self):
        if self.btn_baixar.text() == "BAIXAR":
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
        self.btn_baixar.setStyleSheet("""
            QPushButton { background-color: #DC3545; color: white; border-radius: 6px; padding: 12px 20px; font-size: 14px; font-weight: bold; }
            QPushButton:hover { background-color: #C82333; }
            QPushButton:disabled { background-color: #F5C6CB; }
        """)

        self.aplicar_status("● Iniciando requisição...", "normal")
        self.progress_bar.hide()
        self.lbl_stats.hide()

        self.worker = DownloadWorker(url, pasta, output_format=formato, active_browser=self.last_active_browser)
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
            self.progress_bar.show()
        elif status == "downloading":
            self.aplicar_status("● Baixando...", "normal")
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(int(dados["percent"]))
            if dados.get("update_text"):
                self.lbl_stats.setText(dados["text"])
        elif status == "processing":
            acao = dados.get("action", "Mesclando e convertendo mídia...")
            self.aplicar_status("● Processando arquivo final (pode levar alguns instantes)...", "normal")
            self.lbl_stats.setText(acao)
            self.progress_bar.setRange(0, 0)

    def finalizar_download(self, status, mensagem):
        self.btn_baixar.setText("BAIXAR")
        self.btn_baixar.setStyleSheet("")
        self.btn_baixar.setEnabled(True)
        self.combo_formato.setEnabled(True)
        self.btn_escolher.setEnabled(True)
        self.progress_bar.setRange(0, 100)

        if status == "sucesso":
            self.aplicar_status("● Download concluído com sucesso!", "sucesso")
            self.progress_bar.setValue(100)
            self.lbl_stats.setText("Processo finalizado.")
            self.input_url.clear()
        elif status == "cancelado":
            self.aplicar_status("● Download cancelado.", "aviso")
            self.progress_bar.hide()
            self.lbl_stats.hide()
        else:
            self.aplicar_status(f"● Erro: {mensagem}", "erro")
            self.progress_bar.hide()
            self.lbl_stats.hide()

    def apply_stylesheet(self):
        estilo = """
            QWidget { background-color: #F8F9FA; font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif; color: #333333; }
            QMenuBar { background-color: #F8F9FA; color: #333333; border-bottom: 1px solid #E9ECEF; font-size: 12px; }
            QMenuBar::item { padding: 4px 8px; background: transparent; }
            QMenuBar::item:selected { background-color: #E9ECEF; border-radius: 4px; }
            QMenu { background-color: #FFFFFF; border: 1px solid #CED4DA; padding: 4px; }
            QMenu::item { padding: 6px 20px; border-radius: 4px; }
            QMenu::item:selected { background-color: #007BFF; color: #FFFFFF; }
            QLabel#titleLabel { font-size: 22px; font-weight: bold; color: #212529; }
            QLabel#subtitleLabel { font-size: 13px; color: #6C757D; margin-bottom: 10px; }
            QLabel#inputLabel { font-size: 12px; font-weight: 600; color: #495057; }
            QLabel#statusLabel { font-size: 12px; font-weight: bold; color: #555555; margin-top: 15px; }
            QLabel#statsLabel { font-size: 11px; color: #6C757D; }
            QLineEdit { background-color: #FFFFFF; border: 1px solid #CED4DA; border-radius: 6px; padding: 10px 12px; font-size: 13px; color: #212529; }
            QLineEdit:focus { border: 2px solid #007BFF; padding: 9px 11px; }
            QComboBox { background-color: #FFFFFF; border: 1px solid #CED4DA; border-radius: 6px; padding: 10px 12px; font-size: 13px; color: #212529; }
            QComboBox:focus { border: 2px solid #007BFF; padding: 9px 11px; }
            QComboBox:disabled { background-color: #E9ECEF; color: #6C757D; }
            QComboBox::drop-down { border: none; width: 24px; }
            QComboBox QAbstractItemView { background-color: #FFFFFF; border: 1px solid #CED4DA; selection-background-color: #007BFF; selection-color: #FFFFFF; outline: 0px; }
            QPushButton#secondaryButton { background-color: #E9ECEF; border: 1px solid #CED4DA; border-radius: 6px; padding: 10px; color: #495057; font-weight: bold; }
            QPushButton#secondaryButton:hover { background-color: #DEE2E6; }
            QPushButton#primaryButton { background-color: #007BFF; border: none; border-radius: 6px; padding: 12px 20px; color: #FFFFFF; font-size: 14px; font-weight: bold; }
            QPushButton#primaryButton:hover { background-color: #0056B3; }
            QPushButton#primaryButton:disabled { background-color: #A5C8ED; color: #F8F9FA; }
            QProgressBar { border: 1px solid #CED4DA; border-radius: 6px; background-color: #E9ECEF; height: 12px; }
            QProgressBar::chunk { background-color: #007BFF; border-radius: 5px; }
        """
        self.setStyleSheet(estilo)