# VideoDownloader

O **VideoDownloader** é um aplicativo desktop desenvolvido para o Windows que permite o download e a extração de mídias (vídeo e áudio) em múltiplos formatos, garantindo compatibilidade por meio de extração de cookies e impersonação de navegador.

Este repositório hospeda o **código-fonte** da aplicação e a **distribuição oficial** de suas releases.

## Tecnologias Utilizadas
* **Linguagem:** Python
* **Interface Gráfica:** PySide6 (Qt)
* **Motor de Download:** yt-dlp
* **Processamento de Mídia:** FFmpeg
* **Bypass e Impersonação:** curl_cffi
* **Empacotamento:** PyInstaller (ONEDIR)
* **Instalador:** Inno Setup 7

## Como Configurar o Ambiente de Desenvolvimento

1. Certifique-se de ter o Python instalado.
2. Crie e ative um ambiente virtual:
   ```cmd
   python -m venv .venv
   .venv\Scripts\activate