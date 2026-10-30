import sys
from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor
from PySide6.QtSvg import QSvgRenderer


def _render_svg_pixmap(svg_str: str, width: int, height: int) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(svg_str.strip().encode("utf-8")))
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter)
    painter.end()
    return pixmap


def _render_svg_icon(svg_str: str, size: int = 24) -> QIcon:
    pixmap = _render_svg_pixmap(svg_str, size, size)
    return QIcon(pixmap)


def get_app_icon_pixmap(size: int = 56) -> QPixmap:
    """Retorna o ícone principal do VideoDownloader (retângulo azul arredondado com seta e bandeja)."""
    svg = f"""
    <svg viewBox="0 0 56 56" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="appBg" x1="0" y1="0" x2="56" y2="56" gradientUnits="userSpaceOnUse">
          <stop stop-color="#0080FF"/>
          <stop offset="1" stop-color="#0066D6"/>
        </linearGradient>
      </defs>
      <rect width="56" height="56" rx="14" fill="url(#appBg)"/>
      <!-- Seta de download -->
      <path d="M28 14V32M28 32L20.5 24.5M28 32L35.5 24.5" stroke="white" stroke-width="3.6" stroke-linecap="round" stroke-linejoin="round"/>
      <!-- Bandeja com cantos arredondados -->
      <path d="M17 33.5V36.5C17 37.88 18.12 39 19.5 39H36.5C37.88 39 39 37.88 39 36.5V33.5" stroke="white" stroke-width="3.6" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
    """
    return _render_svg_pixmap(svg, size, size)


def get_home_icon(color: str = "#64748B", size: int = 24, filled: bool = False) -> QIcon:
    if filled:
        svg = f"""
        <svg viewBox="0 0 24 24" fill="{color}" xmlns="http://www.w3.org/2000/svg">
          <path d="M12 3L3 10.5V20C3 20.55 3.45 21 4 21H9V15H15V21H20C20.55 21 21 20.55 21 20V10.5L12 3Z"/>
        </svg>
        """
    else:
        svg = f"""
        <svg viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg">
          <path d="M3 10.5L12 3L21 10.5V20C21 20.55 20.55 21 20 21H15V15H9V21H4C3.45 21 3 20.55 3 20V10.5Z"/>
        </svg>
        """
    return _render_svg_icon(svg, size)


def get_settings_icon(color: str = "#64748B", size: int = 24) -> QIcon:
    svg = f"""
    <svg viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg">
      <circle cx="12" cy="12" r="3.2"/>
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
    </svg>
    """
    return _render_svg_icon(svg, size)


def get_info_icon(color: str = "#64748B", size: int = 24) -> QIcon:
    svg = f"""
    <svg viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg">
      <circle cx="12" cy="12" r="9.5"/>
      <line x1="12" y1="16" x2="12" y2="11.5"/>
      <circle cx="12" cy="8" r="0.8" fill="{color}"/>
    </svg>
    """
    return _render_svg_icon(svg, size)


def get_link_icon(color: str = "#94A3B8", size: int = 18) -> QIcon:
    svg = f"""
    <svg viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg">
      <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
      <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
    </svg>
    """
    return _render_svg_icon(svg, size)


def get_folder_icon(color: str = "#0078D7", size: int = 18) -> QIcon:
    svg = f"""
    <svg viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg">
      <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
    </svg>
    """
    return _render_svg_icon(svg, size)


def get_folder_pixmap(color: str = "#0078D7", size: int = 18) -> QPixmap:
    svg = f"""
    <svg viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg">
      <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
    </svg>
    """
    return _render_svg_pixmap(svg, size, size)


def get_document_icon(color: str = "#0078D7", size: int = 18) -> QIcon:
    svg = f"""
    <svg viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
      <polyline points="14 2 14 8 20 8"/>
    </svg>
    """
    return _render_svg_icon(svg, size)


def get_document_pixmap(color: str = "#0078D7", size: int = 18) -> QPixmap:
    svg = f"""
    <svg viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
      <polyline points="14 2 14 8 20 8"/>
    </svg>
    """
    return _render_svg_pixmap(svg, size, size)


def get_download_button_icon(color: str = "white", size: int = 20) -> QIcon:
    svg = f"""
    <svg viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg">
      <path d="M12 3v12M12 15l-5-5M12 15l5-5"/>
      <path d="M5 20h14"/>
    </svg>
    """
    return _render_svg_icon(svg, size)


def get_sun_icon_pixmap(color: str = "#FFFFFF", size: int = 16) -> QPixmap:
    svg = f"""
    <svg viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg">
      <circle cx="12" cy="12" r="4.2"/>
      <path d="M12 2v2.5M12 19.5v2.5M4.93 4.93l1.8 1.8M17.27 17.27l1.8 1.8M2 12h2.5M19.5 12H22M6.73 17.27l-1.8 1.8M19.07 4.93l-1.8 1.8"/>
    </svg>
    """
    return _render_svg_pixmap(svg, size, size)


def get_moon_icon_pixmap(color: str = "#8A94A6", size: int = 16) -> QPixmap:
    svg = f"""
    <svg viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
    </svg>
    """
    return _render_svg_pixmap(svg, size, size)


def get_chevron_down_pixmap(color: str = "#64748B", size: int = 12) -> QPixmap:
    svg = f"""
    <svg viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg">
      <polyline points="6 9 12 15 18 9"/>
    </svg>
    """
    return _render_svg_pixmap(svg, size, size)
