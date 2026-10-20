# VideoDownloader

<p align="center">
  <strong>Seus vídeos e áudios favoritos, em um só lugar.</strong>
  <br>
  Um aplicativo desktop para Windows, desenvolvido em Python, com uma interface simples para baixar mídias em diferentes formatos.
</p>

<p align="center">
  <a href="https://github.com/hiskjuc/VideoDownloader-Updates/releases/latest/download/VideoDownloader_Setup.exe">
    <img src="https://img.shields.io/badge/Windows-Baixar%20instalador-0078D4?style=for-the-badge&logo=windows&logoColor=white" alt="Baixar para Windows">
  </a>
  <img src="https://img.shields.io/badge/Celular-Em%20breve-555555?style=for-the-badge&logo=android&logoColor=white" alt="Versão para celular em breve">
</p>

<p align="center">
  <a href="https://github.com/hiskjuc/VideoDownloader-Updates/releases">Todas as versões</a>
  ·
  <a href="https://github.com/yt-dlp/yt-dlp">Projeto yt-dlp</a>
</p>

---

## 📥 Downloads

| Plataforma | Disponibilidade | Ação |
|:--|:--:|:--|
| 🪟 **Windows** | Disponível | [Baixar instalador](https://github.com/hiskjuc/VideoDownloader-Updates/releases/latest/download/VideoDownloader_Setup.exe) |
| 📱 **Celular** | Em breve | Versão em desenvolvimento |

**Como instalar no Windows**
1. Baixe o instalador pelo link acima.
2. Execute o arquivo `VideoDownloader_Setup.exe`.
3. Siga as instruções do instalador.

> O link de download aponta para a release mais recente. Para consultar versões anteriores, acesse a [página de releases](https://github.com/hiskjuc/VideoDownloader-Updates/releases).

## ✨ Sobre o projeto

O VideoDownloader nasceu da vontade de tornar a experiência de baixar mídias mais acessível por meio de uma aplicação desktop própria, aproveitando ferramentas já consolidadas da comunidade.

O objetivo é oferecer uma interface gráfica prática para utilizar recursos de download e extração de áudio e vídeo sem depender exclusivamente do terminal.

## 🛠️ Tecnologias

- **[Python](https://www.python.org/)** — linguagem principal.
- **[PySide6](https://doc.qt.io/qtforpython-6/)** — interface gráfica.
- **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** — motor de download de mídias.
- **[FFmpeg](https://ffmpeg.org/)** — processamento e conversão de áudio e vídeo.
- **[curl_cffi](https://github.com/lexiforest/curl_cffi)** — recursos de impersonação de navegador.
- **[PyInstaller](https://pyinstaller.org/)** — empacotamento da aplicação.
- **[Inno Setup](https://jrsoftware.org/isinfo.php)** — criação do instalador para Windows.

## 💙 Créditos e agradecimentos

Um agradecimento especial aos desenvolvedores e colaboradores do **[yt-dlp](https://github.com/yt-dlp/yt-dlp)**.

O projeto começou justamente a partir do contato com essa ferramenta, que serviu de inspiração para criar uma aplicação própria com interface gráfica. O yt-dlp é uma peça fundamental do VideoDownloader, e este projeto reconhece o trabalho da comunidade que o mantém.

O VideoDownloader é um projeto independente e não é um produto oficial do yt-dlp.

## 👨‍💻 Desenvolvimento

Para executar o projeto a partir do código-fonte:

1. Instale o Python e o Git.
2. Clone o repositório:

   ```bash
   git clone https://github.com/hiskjuc/VideoDownloader-Updates.git
   cd VideoDownloader-Updates
   ```

3. Crie e ative um ambiente virtual:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

4. Instale as dependências:

   ```bash
   python -m pip install -r requirements.txt
   ```

5. Execute a aplicação:

   ```bash
   python main.py
   ```

## 📄 Licença e uso

Consulte as licenças da aplicação e de suas dependências antes de redistribuir versões modificadas. O yt-dlp e as demais ferramentas utilizadas possuem seus próprios termos e licenças.

---

<p align="center">
  Feito com dedicação e com a ajuda de projetos open source.
</p>