"""
Widgets personalizados para o layout do VideoDownloader:
- ContentBackgroundWidget: container central com pintura da curva suave de fundo
- ThemeToggleWidget: controle pill de alternância entre Light Mode e Dark Mode
- SidebarNavButton: botões da barra lateral vertical com estado ativo/inativo
"""

from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtWidgets import QWidget, QPushButton
from PySide6.QtGui import (
    QPainter, QColor, QPainterPath, QLinearGradient, QMouseEvent
)

from ui.icons import (
    get_sun_icon_pixmap, get_moon_icon_pixmap,
    get_home_icon, get_settings_icon, get_info_icon
)
from ui.theme import get_theme_palette


class ContentBackgroundWidget(QWidget):
    """
    Widget container com pintura personalizada que reproduz a suave
    onda decorativa no canto superior direito conforme a imagem de referência.
    """
    def __init__(self, theme: str = "light", parent: QWidget = None):
        super().__init__(parent)
        self.theme = theme
        self.setAttribute(Qt.WA_OpaquePaintEvent, False)

    def set_theme(self, theme: str):
        self.theme = theme
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        palette = get_theme_palette(self.theme)
        is_dark = (self.theme == "dark")

        # Fundo base da área de conteúdo
        bg_color = QColor(palette["window_bg"])
        painter.fillRect(self.rect(), bg_color)

        # 1. Primeira curva decorativa mais ampla
        path1 = QPainterPath()
        path1.moveTo(w * 0.42, 0)
        path1.cubicTo(w * 0.62, h * 0.10, w * 0.82, h * 0.26, w, h * 0.32)
        path1.lineTo(w, 0)
        path1.closeSubpath()

        grad1 = QLinearGradient(w * 0.5, 0, w, h * 0.35)
        if is_dark:
            grad1.setColorAt(0.0, QColor(36, 44, 56, 140))
            grad1.setColorAt(1.0, QColor(24, 31, 42, 170))
        else:
            grad1.setColorAt(0.0, QColor(228, 238, 252, 170))
            grad1.setColorAt(1.0, QColor(212, 228, 250, 150))

        painter.fillPath(path1, grad1)

        # 2. Segunda curva mais suave e sobreposta
        path2 = QPainterPath()
        path2.moveTo(w * 0.58, 0)
        path2.cubicTo(w * 0.72, h * 0.08, w * 0.88, h * 0.18, w, h * 0.22)
        path2.lineTo(w, 0)
        path2.closeSubpath()

        grad2 = QLinearGradient(w * 0.6, 0, w, h * 0.25)
        if is_dark:
            grad2.setColorAt(0.0, QColor(44, 55, 72, 120))
            grad2.setColorAt(1.0, QColor(30, 40, 54, 140))
        else:
            grad2.setColorAt(0.0, QColor(238, 245, 255, 140))
            grad2.setColorAt(1.0, QColor(222, 236, 254, 120))

        painter.fillPath(path2, grad2)
        painter.end()


class ThemeToggleWidget(QWidget):
    """
    Controle pill para alternar entre Light Mode e Dark Mode.
    No modo Claro: círculo azul na esquerda com sol branco; lua cinza na direita.
    No modo Escuro: sol cinza na esquerda; círculo azul na direita com lua branca.
    """
    theme_toggled = Signal(str)

    def __init__(self, current_theme: str = "light", parent: QWidget = None):
        super().__init__(parent)
        self.theme = current_theme
        self.setFixedSize(62, 28)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Alternar tema (Claro / Escuro)")

    def set_theme(self, theme: str):
        if self.theme != theme:
            self.theme = theme
            self.update()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            new_theme = "dark" if self.theme == "light" else "light"
            self.theme = new_theme
            self.update()
            self.theme_toggled.emit(new_theme)
        super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        is_dark = (self.theme == "dark")

        # Fundo do pill
        bg_color = QColor("#282F38") if is_dark else QColor("#DCE4F0")
        border_color = QColor("#36404D") if is_dark else QColor("#CCD7E6")

        painter.setBrush(bg_color)
        painter.setPen(border_color)
        painter.drawRoundedRect(0.5, 0.5, 61.0, 27.0, 13.5, 13.5)

        # Indicador circular azul ativo
        indicator_x = 36.5 if is_dark else 2.5
        painter.setBrush(QColor("#0078D7"))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QRectF(indicator_x, 2.5, 23.0, 23.0))

        # Ícone do Sol (esquerda)
        sun_color = "#FFFFFF" if not is_dark else "#8A94A6"
        sun_pm = get_sun_icon_pixmap(color=sun_color, size=15)
        painter.drawPixmap(6, 6, sun_pm)

        # Ícone da Lua (direita)
        moon_color = "#FFFFFF" if is_dark else "#64748B"
        moon_pm = get_moon_icon_pixmap(color=moon_color, size=15)
        painter.drawPixmap(40, 6, moon_pm)

        painter.end()


class SidebarNavButton(QPushButton):
    """
    Botão de navegação da barra lateral vertical.
    Possui dimensões 44x44, cantos arredondados e suporte a estado ativo/inativo.
    """
    def __init__(self, page_index: int, icon_type: str, tooltip: str = "", parent: QWidget = None):
        super().__init__(parent)
        self.page_index = page_index
        self.icon_type = icon_type  # 'home', 'settings', 'info'
        self.is_active = False
        self.current_theme = "light"

        self.setFixedSize(44, 44)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(tooltip)
        self.setProperty("class", "navButton")

    def set_theme_and_active(self, theme: str, is_active: bool):
        self.current_theme = theme
        self.is_active = is_active
        self.setProperty("active", "true" if is_active else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        self._update_icon()

    def _update_icon(self):
        palette = get_theme_palette(self.current_theme)
        if self.is_active:
            icon_color = "#FFFFFF"
            filled = True
        else:
            icon_color = palette["nav_icon_inactive"]
            filled = False

        if self.icon_type == "home":
            self.setIcon(get_home_icon(color=icon_color, size=24, filled=filled))
        elif self.icon_type == "settings":
            self.setIcon(get_settings_icon(color=icon_color, size=24))
        elif self.icon_type == "info":
            self.setIcon(get_info_icon(color=icon_color, size=24))
        self.setIconSize(self.icon().actualSize(self.size()))
