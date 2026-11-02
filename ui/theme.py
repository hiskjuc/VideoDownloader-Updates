"""
Definições de temas (Light Mode e Dark Mode) para o VideoDownloader.
Contém paleta de cores, classes de estilo QSS e utilitários de tema.
"""

LIGHT_PALETTE = {
    "window_bg": "#EEF2F8",
    "sidebar_bg": "#F8FAFD",
    "sidebar_border": "#E2E8F0",
    "card_bg": "#FFFFFF",
    "card_border": "#E2E8F0",
    "subcard_bg": "#F8FAFC",
    "subcard_border": "#E2E8F0",
    "text_primary": "#1E293B",
    "text_secondary": "#64748B",
    "text_muted": "#94A3B8",
    "input_bg": "#FFFFFF",
    "input_border": "#CBD5E1",
    "input_focus_border": "#0078D7",
    "accent_blue": "#0078D7",
    "accent_blue_hover": "#0069BA",
    "accent_blue_pressed": "#005A9E",
    "accent_blue_disabled": "#A5C8ED",
    "progress_groove": "#DCE4F0",
    "progress_chunk": "#0078D7",
    "status_dot_normal": "#0078D7",
    "status_dot_success": "#10B981",
    "status_dot_error": "#EF4444",
    "status_dot_warning": "#F59E0B",
    "button_cancel": "#DC3545",
    "button_cancel_hover": "#C82333",
    "nav_active_bg": "#0078D7",
    "nav_hover_bg": "#E9ECEF",
    "nav_icon_inactive": "#64748B",
    "nav_icon_active": "#FFFFFF",
    "wave_color_1": "rgba(225, 236, 252, 0.7)",
    "wave_color_2": "rgba(215, 230, 250, 0.5)",
    "warning_box_bg": "#FFFBEB",
    "warning_box_border": "#FDE68A",
    "warning_title": "#92400E",
    "warning_text": "#78350F",
    "warning_icon": "#D97706",
}

DARK_PALETTE = {
    "window_bg": "#161B22",
    "sidebar_bg": "#1C2128",
    "sidebar_border": "#30363D",
    "card_bg": "#21262D",
    "card_border": "#30363D",
    "subcard_bg": "#1A1F26",
    "subcard_border": "#30363D",
    "text_primary": "#F0F6FC",
    "text_secondary": "#8B949E",
    "text_muted": "#6E7681",
    "input_bg": "#161B22",
    "input_border": "#30363D",
    "input_focus_border": "#388BFD",
    "accent_blue": "#0078D7",
    "accent_blue_hover": "#0069BA",
    "accent_blue_pressed": "#005A9E",
    "accent_blue_disabled": "#234164",
    "progress_groove": "#30363D",
    "progress_chunk": "#0078D7",
    "status_dot_normal": "#388BFD",
    "status_dot_success": "#22C55E",
    "status_dot_error": "#EF4444",
    "status_dot_warning": "#F59E0B",
    "button_cancel": "#DC3545",
    "button_cancel_hover": "#C82333",
    "nav_active_bg": "#0078D7",
    "nav_hover_bg": "#2D333B",
    "nav_icon_inactive": "#8B949E",
    "nav_icon_active": "#FFFFFF",
    "wave_color_1": "rgba(35, 45, 60, 0.6)",
    "wave_color_2": "rgba(28, 38, 52, 0.4)",
    "warning_box_bg": "rgba(245, 158, 11, 0.10)",
    "warning_box_border": "rgba(245, 158, 11, 0.30)",
    "warning_title": "#FBBF24",
    "warning_text": "#D6D3D1",
    "warning_icon": "#F59E0B",
}


def get_theme_palette(theme: str) -> dict:
    if theme == "dark":
        return DARK_PALETTE
    return LIGHT_PALETTE


def get_theme_stylesheet(theme: str) -> str:
    p = get_theme_palette(theme)

    return f"""
    QWidget {{
        font-family: "Segoe UI", "SF Pro Display", -apple-system, BlinkMacSystemFont, Arial, sans-serif;
        color: {p["text_primary"]};
        outline: none;
    }}

    /* Janela principal e containers */
    #mainWindowWidget {{
        background-color: {p["window_bg"]};
    }}

    /* Barra lateral */
    #sidebarContainer {{
        background-color: {p["sidebar_bg"]};
        border-right: 1px solid {p["sidebar_border"]};
    }}

    /* Botões da barra lateral */
    QPushButton.navButton {{
        background-color: transparent;
        border: none;
        border-radius: 12px;
        padding: 0px;
    }}
    QPushButton.navButton:hover {{
        background-color: {p["nav_hover_bg"]};
    }}
    QPushButton.navButton[active="true"] {{
        background-color: {p["nav_active_bg"]};
    }}

    /* Cartão principal da área central */
    #mainCard {{
        background-color: {p["card_bg"]};
        border: 1px solid {p["card_border"]};
        border-radius: 14px;
    }}

    /* Subcartões para Pasta e Formato */
    #subCard {{
        background-color: {p["subcard_bg"]};
        border: 1px solid {p["subcard_border"]};
        border-radius: 10px;
    }}

    /* Tipografia de Título e Subtítulo */
    #headerTitle {{
        font-size: 22px;
        font-weight: 700;
        color: {p["text_primary"]};
        letter-spacing: -0.3px;
    }}
    #headerSubtitle {{
        font-size: 13px;
        color: {p["text_secondary"]};
        margin-top: 2px;
    }}

    /* Rótulos dos campos */
    #fieldLabel {{
        font-size: 13px;
        font-weight: 600;
        color: {p["text_primary"]};
    }}
    #subCardLabel {{
        font-size: 12px;
        font-weight: 600;
        color: {p["text_primary"]};
    }}

    /* Campo de URL */
    #urlInput {{
        background-color: {p["input_bg"]};
        border: 1.5px solid {p["input_focus_border"]};
        border-radius: 8px;
        padding: 10px 14px;
        font-size: 13px;
        color: {p["text_primary"]};
        selection-background-color: {p["accent_blue"]};
        selection-color: #FFFFFF;
    }}
    #urlInput:focus {{
        border: 1.5px solid {p["input_focus_border"]};
    }}

    /* Campo de pasta */
    #folderInput {{
        background-color: {p["input_bg"]};
        border: 1px solid {p["input_border"]};
        border-radius: 6px;
        padding: 8px 10px;
        font-size: 12px;
        color: {p["text_primary"]};
    }}
    #folderInput:focus {{
        border: 1px solid {p["input_focus_border"]};
    }}

    /* Botão de escolher pasta */
    #btnBrowse {{
        background-color: {p["card_bg"]};
        border: 1px solid {p["input_border"]};
        border-radius: 6px;
        padding: 6px;
    }}
    #btnBrowse:hover {{
        background-color: {p["subcard_bg"]};
        border-color: {p["input_focus_border"]};
    }}

    /* Combobox de Formato */
    #formatCombo {{
        background-color: {p["input_bg"]};
        border: 1px solid {p["input_border"]};
        border-radius: 6px;
        padding: 6px 12px;
        min-height: 20px;
        font-size: 12px;
        color: {p["text_primary"]};
    }}
    #formatCombo:focus {{
        border: 1px solid {p["input_focus_border"]};
    }}
    #formatCombo:disabled {{
        background-color: {p["subcard_bg"]};
        color: {p["text_muted"]};
    }}
    #formatCombo::drop-down {{
        border: none;
        width: 24px;
        subcontrol-origin: padding;
        subcontrol-position: top right;
    }}
    #formatCombo QAbstractItemView {{
        background-color: {p["card_bg"]};
        border: 1px solid {p["card_border"]};
        border-radius: 8px;
        padding: 4px;
        color: {p["text_primary"]};
        selection-background-color: {p["accent_blue"]};
        selection-color: #FFFFFF;
        outline: 0px;
    }}

    /* Botão Principal BAIXAR */
    #primaryButton {{
        background-color: {p["accent_blue"]};
        border: none;
        border-radius: 8px;
        padding: 12px 24px;
        color: #FFFFFF;
        font-size: 14px;
        font-weight: 700;
        letter-spacing: 0.3px;
    }}
    #primaryButton:hover {{
        background-color: {p["accent_blue_hover"]};
    }}
    #primaryButton:pressed {{
        background-color: {p["accent_blue_pressed"]};
    }}
    #primaryButton:disabled {{
        background-color: {p["accent_blue_disabled"]};
        color: {p["text_muted"]};
    }}

    /* Área inferior de status */
    #statusLabel {{
        font-size: 12px;
        font-weight: 500;
        color: {p["text_secondary"]};
    }}
    #percentLabel {{
        font-size: 12px;
        font-weight: 600;
        color: {p["text_secondary"]};
    }}
    #statsLabel {{
        font-size: 11px;
        color: {p["text_muted"]};
    }}

    /* Barra de progresso horizontal */
    QProgressBar#progressBar {{
        border: none;
        border-radius: 4px;
        background-color: {p["progress_groove"]};
        height: 8px;
        text-align: center;
    }}
    QProgressBar#progressBar::chunk {{
        background-color: {p["progress_chunk"]};
        border-radius: 4px;
    }}

    /* Telas de Configurações e Informações */
    #pageTitle {{
        font-size: 18px;
        font-weight: 700;
        color: {p["text_primary"]};
    }}
    #pageSubtitle {{
        font-size: 12px;
        color: {p["text_secondary"]};
        margin-bottom: 8px;
    }}
    #settingSectionTitle {{
        font-size: 13px;
        font-weight: 600;
        color: {p["text_primary"]};
        margin-bottom: 2px;
    }}
    #settingSectionDesc {{
        font-size: 12px;
        color: {p["text_secondary"]};
        margin-bottom: 6px;
    }}
    QPushButton#secondaryActionButton {{
        background-color: {p["card_bg"]};
        border: 1px solid {p["card_border"]};
        border-radius: 6px;
        padding: 8px 16px;
        color: {p["text_primary"]};
        font-size: 12px;
        font-weight: 600;
        min-height: 16px;
    }}
    QPushButton#secondaryActionButton:hover {{
        background-color: {p["nav_hover_bg"]};
        border-color: {p["accent_blue"]};
    }}
    QPushButton#secondaryActionButton[active="true"] {{
        background-color: {p["accent_blue"]};
        color: #FFFFFF;
        border-color: {p["accent_blue"]};
    }}


    /* Seletor Segmentado de Modo (Vídeo / Somente Áudio) */
    #modeSelectorContainer {{
        background-color: {p["subcard_bg"]};
        border: 1px solid {p["subcard_border"]};
        border-radius: 8px;
        padding: 3px;
    }}
    QPushButton.modeButton {{
        background-color: transparent;
        color: {p["text_secondary"]};
        border: none;
        border-radius: 6px;
        font-size: 12px;
        font-weight: 600;
        padding: 6px 16px;
        min-height: 18px;
    }}
    QPushButton.modeButton:hover {{
        color: {p["text_primary"]};
        background-color: {p["card_bg"]};
    }}
    QPushButton.modeButton[active="true"] {{
        background-color: {p["accent_blue"]};
        color: #FFFFFF;
    }}
    QPushButton.modeButton[active="true"]:hover {{
        background-color: {p["accent_blue_hover"]};
    }}

    /* Combobox de Qualidade / Resolução */
    #qualityCombo {{
        background-color: {p["input_bg"]};
        border: 1px solid {p["input_border"]};
        border-radius: 6px;
        padding: 6px 12px;
        min-height: 20px;
        font-size: 12px;
        color: {p["text_primary"]};
    }}
    #qualityCombo:focus {{
        border: 1px solid {p["input_focus_border"]};
    }}
    #qualityCombo:disabled {{
        background-color: {p["subcard_bg"]};
        color: {p["text_muted"]};
    }}
    #qualityCombo::drop-down {{
        border: none;
        width: 24px;
        subcontrol-origin: padding;
        subcontrol-position: top right;
    }}
    #qualityCombo QAbstractItemView {{
        background-color: {p["card_bg"]};
        border: 1px solid {p["card_border"]};
        selection-background-color: {p["accent_blue"]};
        selection-color: #FFFFFF;
        padding: 4px;
        border-radius: 6px;
    }}

    /* Painel e Controles de Upscaling (FFmpeg Lanczos) */
    #upscaleContainer {{
        background-color: {p["subcard_bg"]};
        border: 1px solid {p["subcard_border"]};
        border-radius: 8px;
        padding: 6px 12px;
    }}
    QCheckBox#upscaleCheckBox {{
        font-size: 12px;
        font-weight: 600;
        color: {p["text_primary"]};
        spacing: 8px;
    }}
    QCheckBox#upscaleCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border-radius: 4px;
        border: 1.5px solid {p["input_border"]};
        background-color: {p["input_bg"]};
    }}
    QCheckBox#upscaleCheckBox::indicator:hover {{
        border-color: {p["accent_blue"]};
    }}
    QCheckBox#upscaleCheckBox::indicator:checked {{
        background-color: {p["accent_blue"]};
        border-color: {p["accent_blue"]};
    }}
    #upscaleCombo {{
        background-color: {p["input_bg"]};
        border: 1px solid {p["input_border"]};
        border-radius: 6px;
        padding: 4px 10px;
        min-height: 18px;
        font-size: 12px;
        color: {p["text_primary"]};
    }}
    #upscaleCombo:focus {{
        border: 1px solid {p["input_focus_border"]};
    }}
    #upscaleCombo:disabled {{
        background-color: {p["subcard_bg"]};
        color: {p["text_muted"]};
    }}
    #upscaleCombo::drop-down {{
        border: none;
        width: 20px;
        subcontrol-origin: padding;
        subcontrol-position: top right;
    }}
    #upscaleCombo QAbstractItemView {{
        background-color: {p["card_bg"]};
        border: 1px solid {p["card_border"]};
        selection-background-color: {p["accent_blue"]};
        selection-color: #FFFFFF;
        padding: 4px;
        border-radius: 6px;
    }}
    #upscaleInfoLabel {{
        color: {p["text_muted"]};
        font-size: 13px;
        padding: 2px;
    }}
    #upscaleInfoLabel:hover {{
        color: {p["accent_blue"]};
    }}

    /* Aviso de alto consumo de CPU no Upscaling */
    #upscaleWarningBox {{
        background-color: {p["warning_box_bg"]};
        border: 1px solid {p["warning_box_border"]};
        border-radius: 6px;
        margin-top: 4px;
    }}
    #upscaleWarningTitle {{
        font-size: 11px;
        font-weight: 700;
        color: {p["warning_title"]};
    }}
    #upscaleWarningBody {{
        font-size: 11px;
        color: {p["warning_text"]};
    }}

    /* Badges e tags */
    #versionBadge {{
        background-color: {p["card_bg"]};
        border: 1.5px solid {p["accent_blue"]};
        border-radius: 12px;
        padding: 4px 14px;
        font-size: 12px;
        font-weight: 700;
        color: {p["accent_blue"]};
    }}
    """
