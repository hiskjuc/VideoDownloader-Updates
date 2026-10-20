import yt_dlp
import pathlib
import os
import traceback
import ctypes
import subprocess
from yt_dlp.networking.impersonate import ImpersonateTarget

class DownloadCancelled(Exception):
    pass

VIDEO_FORMATS = {'mp4', 'mkv', 'webm', 'mov', 'avi'}
AUDIO_FORMATS = {'mp3', 'm4a', 'wav', 'flac', 'opus'}

def build_format_options(output_format: str) -> dict:
    """
    Constrói e retorna as opções específicas de formato e pós-processamento para o yt-dlp.
    """
    fmt = (output_format or 'mp4').lower().strip()
    opts = {}

    if fmt in AUDIO_FORMATS:
        # Baixa apenas o melhor stream de áudio disponível (sem vídeo)
        opts['format'] = 'bestaudio/best'

        pp = {
            'key': 'FFmpegExtractAudio',
            'preferredcodec': fmt,
        }
        # Aplica configurações de qualidade apropriadas apenas para formatos com perdas (lossy)
        # Para WAV e FLAC (lossless), omitimos preferredquality para não passar parâmetros indevidos
        if fmt == 'mp3':
            pp['preferredquality'] = '192'
        elif fmt in ('m4a', 'opus'):
            pp['preferredquality'] = '0'  # 0 no yt-dlp indica a melhor qualidade VBR/padrão do extrator

        opts['postprocessors'] = [pp]

    else:
        if fmt not in VIDEO_FORMATS:
            fmt = 'mp4'

        # Prioriza codecs nativamente compatíveis com o contêiner quando possível para permitir
        # remux rápido sem recodificação, mantendo fallback para qualquer melhor stream disponível
        if fmt == 'mp4':
            opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best'
            opts['merge_output_format'] = 'mp4'
        elif fmt == 'webm':
            opts['format'] = 'bestvideo[ext=webm]+bestaudio[ext=webm]/bestvideo+bestaudio/best'
            opts['merge_output_format'] = 'webm'
        elif fmt == 'mkv':
            opts['format'] = 'bestvideo+bestaudio/best'
            opts['merge_output_format'] = 'mkv'
        else:
            # MOV e AVI não são alvos diretos de merge_output_format em todas as situações,
            # então dependem do FFmpegVideoConvertor
            opts['format'] = 'bestvideo+bestaudio/best'

        # Garante que o arquivo final seja convertido pelo FFmpeg caso o simples remux/merge
        # não produza o contêiner solicitado (essencial para MOV, AVI ou streams incompatíveis)
        opts['postprocessors'] = [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': fmt,
        }]

    return opts


def get_foreground_browser():
    """
    Descobre o navegador caso a janela atualmente em foco (Foreground) seja um navegador compatível.
    """
    browser_map = {
        'chrome.exe': 'chrome',
        'msedge.exe': 'edge',
        'firefox.exe': 'firefox',
        'brave.exe': 'brave',
        'opera.exe': 'opera',
        'vivaldi.exe': 'vivaldi'
    }

    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        hwnd = user32.GetForegroundWindow()
        if hwnd:
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


def get_fallback_browser():
    """
    Procura na lista de processos em execução pela ordem de prioridade.
    """
    browser_map = {
        'chrome.exe': 'chrome',
        'msedge.exe': 'edge',
        'firefox.exe': 'firefox',
        'brave.exe': 'brave',
        'opera.exe': 'opera',
        'vivaldi.exe': 'vivaldi'
    }
    priority_order = ['chrome', 'edge', 'firefox', 'brave', 'opera', 'vivaldi']

    try:
        output = subprocess.check_output('tasklist /NH /FO CSV', shell=True, text=True, creationflags=0x08000000)
        running_exes = [line.split(',')[0].strip('"').lower() for line in output.splitlines() if line]

        running_browsers = set()
        for exe in running_exes:
            if exe in browser_map:
                running_browsers.add(browser_map[exe])

        for b in priority_order:
            if b in running_browsers:
                return b
    except Exception:
        pass

    return None


def download_video(url: str, dest_folder: str, output_format: str = "mp4", progress_callback=None, is_cancelled=None, active_browser=None):
    """
    Realiza o download e conversão de mídia na URL informada.
    Retorna uma tupla (status: str, mensagem: str)
    """
    pasta_destino = pathlib.Path(dest_folder).resolve()
    fmt = (output_format or "mp4").lower().strip()
    is_audio = fmt in AUDIO_FORMATS

    try:
        pasta_destino.mkdir(parents=True, exist_ok=True)
    except PermissionError as e:
        print(f"ERRO DE PERMISSÃO: {e}")
        return "erro", "Sem permissão para salvar na pasta de destino."
    except OSError as e:
        print(f"ERRO DE SO: {e}")
        return "erro", "O caminho de destino é inválido ou inacessível."

    arquivos_rastreados = set()

    def _limpar_arquivos_parciais():
        """Remove arquivos incompletos ou temporários caso o download seja cancelado."""
        all_exts = ['', '.part', '.ytdl'] + [f'.{ext}' for ext in (VIDEO_FORMATS | AUDIO_FORMATS)]
        for f in list(arquivos_rastreados):
            p = pathlib.Path(str(f))
            stem_base = p.with_suffix('')
            for ext in all_exts:
                for candidate in [pathlib.Path(str(p) + ext), pathlib.Path(str(stem_base) + ext)]:
                    try:
                        if candidate.exists():
                            candidate.unlink()
                    except Exception as e:
                        print(f"Aviso: Não foi possível apagar arquivo temporário: {e}")

    def my_hook(d):
        if is_cancelled and is_cancelled():
            raise DownloadCancelled("Download interrompido pelo usuário.")

        if 'filename' in d and d['filename']:
            arquivos_rastreados.add(d['filename'])
        if 'tmpfilename' in d and d['tmpfilename']:
            arquivos_rastreados.add(d['tmpfilename'])

        if not progress_callback:
            return

        status = d.get('status')
        if status == 'downloading':
            downloaded_bytes = d.get('downloaded_bytes', 0)
            total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            speed = d.get('speed', 0)

            percent = 0.0
            if total_bytes > 0:
                percent = (downloaded_bytes / total_bytes) * 100

            progress_callback({
                'status': 'downloading',
                'percent': percent,
                'downloaded_bytes': downloaded_bytes,
                'total_bytes': total_bytes,
                'speed': speed
            })

        elif status == 'finished':
            acao = f"Extraindo e convertendo áudio para {fmt.upper()}..." if is_audio else f"Processando e convertendo vídeo para {fmt.upper()}..."
            progress_callback({
                'status': 'processing',
                'action': acao
            })

    def my_pp_hook(d):
        if is_cancelled and is_cancelled():
            raise DownloadCancelled("Download interrompido pelo usuário.")

        info_dict = d.get('info_dict') or {}
        if 'filepath' in info_dict and info_dict['filepath']:
            arquivos_rastreados.add(info_dict['filepath'])

        if not progress_callback:
            return

        if d.get('status') == 'started':
            acao = f"Convertendo áudio para {fmt.upper()} (FFmpeg)..." if is_audio else f"Finalizando contêiner {fmt.upper()} (FFmpeg)..."
            progress_callback({
                'status': 'processing',
                'action': acao
            })

    # Usa %(title)s.%(ext)s para que os pós-processadores do yt-dlp substituam a extensão
    # corretamente sem gerar nomes duplicados como video.mp4.mp4
    ydl_opts = {
        'outtmpl': str(pasta_destino / '%(title)s.%(ext)s'),
        'quiet': False,
        'no_warnings': False,
        'verbose': True,
        'impersonate': ImpersonateTarget('chrome', '116', 'windows', '10'),
        'color': 'no_color',
        'noplaylist': True,
    }

    # Mescla as opções específicas de vídeo ou áudio
    ydl_opts.update(build_format_options(fmt))

    browser = active_browser
    if not browser:
        browser = get_fallback_browser()

    if browser:
        print(f"\nNavegador utilizado para cookies: {browser.capitalize()}")
        ydl_opts['cookiesfrombrowser'] = (browser, None, None, None)
    else:
        print("\nNenhum navegador identificado; seguindo sem cookies.")

    if progress_callback or is_cancelled:
        ydl_opts['progress_hooks'] = [my_hook]
        ydl_opts['postprocessor_hooks'] = [my_pp_hook]

    while True:
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:

                if progress_callback:
                    progress_callback({'status': 'extracting'})

                print(f"\n--- Analisando URL (Formato de saída: {fmt.upper()}) ---")
                info = ydl.extract_info(url, download=False)

                if not info:
                    return "erro", "A página não contém uma mídia compatível."

                extractor = info.get('extractor', 'Desconhecido')
                title = info.get('title', 'Sem título')
                duration = info.get('duration', 'N/A')

                print(f"Plataforma/Extractor: {extractor}")
                print(f"Título: {title}")
                print(f"Duração: {duration}s")

                if is_cancelled and is_cancelled():
                    raise DownloadCancelled("Download interrompido pelo usuário.")

                print("--- Iniciando Download ---")
                ydl.download([url])

            return "sucesso", ""

        except DownloadCancelled:
            _limpar_arquivos_parciais()
            return "cancelado", "Download cancelado pelo usuário."

        except yt_dlp.utils.DownloadError as e:
            error_msg = str(e).lower()
            if "interrompido pelo usuário" in error_msg or "downloadcancelled" in error_msg:
                _limpar_arquivos_parciais()
                return "cancelado", "Download cancelado pelo usuário."

            if 'cookiesfrombrowser' in ydl_opts and (
                "database is locked" in error_msg or
                "permission denied" in error_msg or
                "cookie" in error_msg or
                "could not find" in error_msg or
                "sqlite3" in error_msg
            ):
                print(f"\nNão foi possível carregar cookies do navegador. Detalhe técnico: {e}")
                print("Tentando continuar o download sem cookies...")
                del ydl_opts['cookiesfrombrowser']
                continue

            print(f"\nERRO yt-dlp: {e}")

            if "ffmpeg" in error_msg or "ffprobe" in error_msg or "postprocessing" in error_msg or "conversion failed" in error_msg:
                return "erro", f"Falha ao converter para {fmt.upper()}. Verifique se o FFmpeg está instalado e acessível."
            elif "requested format is not available" in error_msg or "no video formats" in error_msg or "no playable video" in error_msg:
                return "erro", "Formato solicitado indisponível ou a página não contém mídia compatível."
            elif "drm" in error_msg or "protected" in error_msg:
                return "erro", "O conteúdo possui uma proteção (DRM) que impede o download."
            elif "login" in error_msg or "authentication" in error_msg or "registered users" in error_msg:
                return "erro", "O vídeo requer autenticação para ser acessado."
            elif "unsupported url" in error_msg or "invalid" in error_msg:
                return "erro", "O site não é suportado ou a URL é inválida."
            elif "unavailable" in error_msg or "not available" in error_msg:
                return "erro", "O vídeo não está disponível ou foi excluído."
            elif "private" in error_msg:
                return "erro", "Este vídeo é privado."
            elif "network" in error_msg or "getaddrinfo" in error_msg:
                return "erro", "Erro de rede. Verifique sua conexão."
            else:
                return "erro", "O download falhou. Verifique a URL e tente novamente."

        except Exception as e:
            error_msg = str(e).lower()
            if "interrompido pelo usuário" in error_msg or "downloadcancelled" in error_msg:
                _limpar_arquivos_parciais()
                return "cancelado", "Download cancelado pelo usuário."

            if 'cookiesfrombrowser' in ydl_opts and (
                "database is locked" in error_msg or
                "permission denied" in error_msg or
                "cookie" in error_msg or
                "could not find" in error_msg or
                "sqlite3" in error_msg
            ):
                print(f"\nNão foi possível carregar cookies do navegador. Detalhe técnico: {e}")
                print("Tentando continuar o download sem cookies...")
                del ydl_opts['cookiesfrombrowser']
                continue

            print("\n===== ERRO INESPERADO DIAGNÓSTICO =====")
            print(f"Tipo: {type(e).__name__}")
            print(f"repr: {repr(e)}")
            print(f"str: {str(e)}")
            print("Traceback completo:")
            traceback.print_exc()
            print("=======================================")

            return "erro", "Ocorreu um erro inesperado. Verifique o console."