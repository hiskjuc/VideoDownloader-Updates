import sys
import yt_dlp
import pathlib
import os
import traceback
import ctypes
import subprocess
import tempfile
import time
import uuid
import re
from yt_dlp.networking.impersonate import ImpersonateTarget

class DownloadCancelled(Exception):
    pass

VIDEO_FORMATS = {'mp4', 'mkv', 'webm', 'mov', 'avi'}
AUDIO_FORMATS = {'mp3', 'm4a', 'wav', 'flac', 'opus'}

VIDEO_RESOLUTIONS = [
    ('best', 'Melhor disponível (padrão)'),
    ('2160p', '2160p (4K)'),
    ('1440p', '1440p (2K)'),
    ('1080p', '1080p (Full HD)'),
    ('720p', '720p (HD)'),
    ('480p', '480p'),
    ('360p', '360p'),
]

AUDIO_BITRATES = [
    ('best', 'Melhor disponível (padrão)'),
    ('320k', '320 kbps (Alta fidelidade)'),
    ('256k', '256 kbps'),
    ('192k', '192 kbps (Padrão)'),
    ('128k', '128 kbps'),
    ('96k', '96 kbps'),
]


def build_format_options(output_format: str, video_quality: str = 'best', audio_quality: str = None) -> dict:
    """
    Constrói e retorna as opções específicas de formato, resolução, qualidade de áudio
    e pós-processamento para o yt-dlp.
    """
    fmt = (output_format or 'mp4').lower().strip()
    opts = {}

    if fmt in AUDIO_FORMATS:
        # Baixa apenas o stream de áudio apropriado (sem vídeo)
        opts['format'] = 'bestaudio/best'

        pp = {
            'key': 'FFmpegExtractAudio',
            'preferredcodec': fmt,
        }
        # Aplica configurações de qualidade apropriadas apenas para formatos com perdas (lossy)
        # Para WAV e FLAC (lossless), omitimos preferredquality para não passar parâmetros indevidos
        if fmt in ('mp3', 'm4a', 'opus'):
            if audio_quality is None:
                pp['preferredquality'] = '192' if fmt == 'mp3' else '0'
            elif audio_quality == 'best':
                pp['preferredquality'] = '0'
            else:
                clean_b = str(audio_quality).lower().replace('k', '').replace('bps', '').strip()
                pp['preferredquality'] = clean_b

        opts['postprocessors'] = [pp]

    else:
        if fmt not in VIDEO_FORMATS:
            fmt = 'mp4'

        v_qual = (video_quality or 'best').lower().strip()

        if v_qual == 'best':
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
                opts['format'] = 'bestvideo+bestaudio/best'
        else:
            try:
                h = int(v_qual.replace('p', ''))
            except ValueError:
                h = None

            if h:
                if fmt == 'mp4':
                    opts['format'] = (
                        f'bestvideo[height={h}][ext=mp4]+bestaudio[ext=m4a]/'
                        f'bestvideo[height={h}]+bestaudio[ext=m4a]/'
                        f'bestvideo[height={h}]+bestaudio/'
                        f'bestvideo[height<={h}][ext=mp4]+bestaudio[ext=m4a]/'
                        f'bestvideo[height<={h}]+bestaudio/'
                        f'best[height<={h}]'
                    )
                    opts['merge_output_format'] = 'mp4'
                elif fmt == 'webm':
                    opts['format'] = (
                        f'bestvideo[height={h}][ext=webm]+bestaudio[ext=webm]/'
                        f'bestvideo[height={h}]+bestaudio[ext=webm]/'
                        f'bestvideo[height={h}]+bestaudio/'
                        f'bestvideo[height<={h}][ext=webm]+bestaudio[ext=webm]/'
                        f'bestvideo[height<={h}]+bestaudio/'
                        f'best[height<={h}]'
                    )
                    opts['merge_output_format'] = 'webm'
                elif fmt == 'mkv':
                    opts['format'] = (
                        f'bestvideo[height={h}]+bestaudio/'
                        f'bestvideo[height<={h}]+bestaudio/'
                        f'best[height<={h}]'
                    )
                    opts['merge_output_format'] = 'mkv'
                else:
                    opts['format'] = (
                        f'bestvideo[height={h}]+bestaudio/'
                        f'bestvideo[height<={h}]+bestaudio/'
                        f'best[height<={h}]'
                    )
            else:
                opts['format'] = 'bestvideo+bestaudio/best'
                if fmt in ('mp4', 'webm', 'mkv'):
                    opts['merge_output_format'] = fmt

        # Garante que o arquivo final seja convertido pelo FFmpeg caso o simples remux/merge
        # não produza o contêiner solicitado (essencial para MOV, AVI ou streams incompatíveis)
        opts['postprocessors'] = [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': fmt,
        }]

    return opts


class MediaInfoLogger:
    """Coletor silencioso de mensagens do yt-dlp para a análise preliminar de URLs."""
    def __init__(self):
        self.errors = []
        self.warnings = []

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        self.warnings.append(msg)

    def error(self, msg):
        self.errors.append(msg)


class DownloadLogger:
    """Logger para o fluxo de download com supressão de mensagens brutas duplicadas de cookies."""
    def __init__(self, suppress_cookie_errors=True):
        self.suppress_cookie_errors = suppress_cookie_errors

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        if self.suppress_cookie_errors and is_cookie_lock_error(msg):
            return
        print(f"\nERRO yt-dlp: {msg}")


def is_cookie_lock_error(err) -> bool:
    """Verifica se o erro é decorrente de bloqueio, ausência ou permissão no banco de cookies do navegador."""
    if not err:
        return False
    msg = str(err).lower()
    return any(keyword in msg for keyword in [
        "could not copy chrome cookie database",
        "database is locked",
        "permission denied",
        "could not find",
        "cookie",
        "sqlite3",
        "cookieloaderror",
        "7271",
    ])


def is_auth_required_error(err) -> bool:
    """Verifica se o erro indica que a mídia exige login, confirmação de idade ou autenticação."""
    if not err:
        return False
    msg = str(err).lower()
    return any(keyword in msg for keyword in [
        "sign in",
        "login",
        "private",
        "members-only",
        "member",
        "bot",
        "confirm your age",
        "account",
        "authenticated",
        "restricted",
        "cookies",
    ])


def extract_media_info(url: str, active_browser: str = None) -> dict:
    """
    Inspeciona a mídia na URL informada para obter título, formatos e resoluções reais disponíveis.
    Executado em segundo plano para não travar a interface do usuário.
    """
    base_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'extract_flat': False,
        'noplaylist': True,
        'impersonate': ImpersonateTarget('chrome', '116', 'windows', '10'),
    }

    ffmpeg_dir = get_ffmpeg_dir()
    if ffmpeg_dir:
        base_opts['ffmpeg_location'] = ffmpeg_dir

    def _executar_extracao(opts):
        logger = MediaInfoLogger()
        current_opts = dict(opts)
        current_opts['logger'] = logger
        try:
            with yt_dlp.YoutubeDL(current_opts) as ydl:
                info_data = ydl.extract_info(url, download=False)
                return info_data, None
        except Exception as e:
            err_detail = " | ".join(logger.errors) if logger.errors else str(e)
            return None, err_detail

    # 1. Tentativa primária: SEM cookies do navegador (URLs públicas funcionam 100% sem cookies e sem bloqueios)
    info, err_msg = _executar_extracao(base_opts)

    # 2. Se falhar sem cookies, tenta com cookies caso haja navegador disponível
    browser = active_browser or get_fallback_browser()
    if not info and browser:
        opts_cookies = dict(base_opts)
        opts_cookies['cookiesfrombrowser'] = (browser, None, None, None)
        info_cookies, err_cookies = _executar_extracao(opts_cookies)

        if info_cookies:
            info = info_cookies
            err_msg = None
        else:
            if is_cookie_lock_error(err_cookies):
                print(f"[MediaInfo] Não foi possível carregar cookies do navegador ({browser.capitalize()}): banco de dados em uso ou protegido.")
                if is_auth_required_error(err_msg):
                    err_msg = f"O vídeo requer autenticação, mas não foi possível ler os cookies do {browser.capitalize()} (feche o navegador para liberar o banco de dados)."
            else:
                err_msg = err_cookies

    try:
        if not info:
            return {'sucesso': False, 'mensagem': err_msg or 'A página não contém informações de mídia compatíveis.'}

        formats = info.get('formats', [])
        eff_heights = set()
        for f in formats:
            if f.get('vcodec') != 'none':
                w = f.get('width') or 0
                h = f.get('height') or 0
                # Em vídeos verticais (ex: 1080x1920), a largura representa o padrão horizontal de resolução
                eff = w if (h > 0 and w > 0 and h > w) else h
                if eff > 0:
                    eff_heights.add(eff)

        tiers = [
            (2160, '2160p', '2160p (4K)', 1800),
            (1440, '1440p', '1440p (2K)', 1200),
            (1080, '1080p', '1080p (Full HD)', 900),
            (720, '720p', '720p (HD)', 600),
            (480, '480p', '480p', 400),
            (360, '360p', '360p', 300),
        ]

        available_res = []
        for target, key, label, min_val in tiers:
            if any(min_val <= h <= target + 100 for h in eff_heights):
                available_res.append((key, label))

        audio_bitrates = [int(f['abr']) for f in formats if f.get('acodec') != 'none' and f.get('abr')]
        max_abr = max(audio_bitrates) if audio_bitrates else None

        return {
            'sucesso': True,
            'url': url,
            'title': info.get('title', 'Sem título'),
            'duration': info.get('duration'),
            'extractor': info.get('extractor', 'Desconhecido'),
            'available_resolutions': available_res,
            'max_height': max(eff_heights) if eff_heights else None,
            'max_audio_bitrate': max_abr,
        }
    except Exception as e:
        return {'sucesso': False, 'mensagem': str(e)}


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


def get_ffmpeg_dir():
    """
    Verifica a presença dos executáveis FFmpeg e FFprobe no diretório do aplicativo.
    Retorna o caminho do diretório se ambos existirem, caso contrário retorna None para usar o PATH.
    """
    candidates = []
    if getattr(sys, 'frozen', False):
        # No PyInstaller (ONEDIR ou ONEFILE), tenta usar _MEIPASS, com fallback para o diretório do executável
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            candidates.append(meipass)
        candidates.append(os.path.dirname(sys.executable))
    else:
        # Ambiente de desenvolvimento local
        candidates.append(os.path.dirname(os.path.abspath(__file__)))

    for base_path in candidates:
        ffmpeg_path = os.path.join(base_path, 'ffmpeg.exe')
        ffprobe_path = os.path.join(base_path, 'ffprobe.exe')

        if os.path.exists(ffmpeg_path) and os.path.exists(ffprobe_path):
            return base_path

    return None


def get_video_dimensions(file_path: pathlib.Path, ffmpeg_dir: str = None) -> tuple[int, int]:
    """Obtém largura e altura do vídeo via ffprobe."""
    probe_bin = "ffprobe"
    if ffmpeg_dir:
        candidate = os.path.join(ffmpeg_dir, "ffprobe.exe" if sys.platform == "win32" else "ffprobe")
        if os.path.exists(candidate):
            probe_bin = candidate

    cmd = [
        probe_bin, "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=p=0",
        str(file_path)
    ]
    creationflags = 0x08000000 if sys.platform == "win32" else 0
    res = subprocess.check_output(cmd, text=True, creationflags=creationflags).strip()
    w, h = [int(x) for x in res.split(",")]
    return w, h


def upscale_video(
    file_path: pathlib.Path,
    target_res: str,
    ffmpeg_dir: str = None,
    progress_callback=None,
    is_cancelled=None
) -> tuple[bool, str]:
    """
    Executa o upscaling do vídeo com FFmpeg utilizando filtro Lanczos de alta precisão.
    Preserva rigorosamente a proporção original, sincronização e a faixa de áudio original sem perda.
    Retorna (sucesso: bool, mensagem_erro: str).
    """
    try:
        target_h = int(str(target_res).lower().replace('p', '').strip())
    except ValueError:
        return False, f"Resolução de destino inválida: {target_res}"

    p = pathlib.Path(file_path)
    if not p.exists():
        return False, "Arquivo original não encontrado para upscaling."

    try:
        w, h = get_video_dimensions(p, ffmpeg_dir=ffmpeg_dir)
    except Exception as e:
        return False, f"Não foi possível inspecionar o vídeo com FFprobe: {e}"

    eff_h = w if (h > 0 and w > 0 and h > w) else h
    if target_h <= eff_h:
        # Resolução original já é igual ou superior: não faz re-encode desnecessário
        return True, f"A resolução original ({eff_h}p) já é maior ou igual ao alvo ({target_h}p)."

    temp_output = p.with_name(f"{p.stem}.upscaled_temp{p.suffix}")
    if temp_output.exists():
        try:
            temp_output.unlink()
        except Exception:
            pass

    ffmpeg_bin = "ffmpeg"
    if ffmpeg_dir:
        candidate = os.path.join(ffmpeg_dir, "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
        if os.path.exists(candidate):
            ffmpeg_bin = candidate

    # Configuração do filtro preservando proporção e dimensões pares (-2)
    if h > w:  # Vídeo vertical (ex: 720x1280 -> 1080x1920)
        scale_filter = f"scale={target_h}:-2:flags=lanczos"
    else:      # Vídeo paisagem (ex: 1280x720 -> 1920x1080)
        scale_filter = f"scale=-2:{target_h}:flags=lanczos"

    cmd = [
        ffmpeg_bin, "-y",
        "-i", str(p),
        "-vf", scale_filter,
        "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-pix_fmt", "yuv420p",
        "-c:a", "copy",
    ]
    if p.suffix.lower() in ('.mp4', '.mov'):
        cmd.extend(["-movflags", "+faststart"])
    cmd.append(str(temp_output))

    creationflags = 0x08000000 if sys.platform == "win32" else 0

    proc = None
    with tempfile.TemporaryFile() as err_f:
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=err_f,
                creationflags=creationflags
            )

            while proc.poll() is None:
                if is_cancelled and is_cancelled():
                    proc.kill()
                    proc.wait()
                    if temp_output.exists():
                        try:
                            temp_output.unlink()
                        except Exception:
                            pass
                    return False, "Processamento cancelado pelo usuário."
                time.sleep(0.2)

            if proc.returncode != 0:
                err_f.seek(0)
                err_text = err_f.read().decode('utf-8', errors='replace')
                if temp_output.exists():
                    try:
                        temp_output.unlink()
                    except Exception:
                        pass
                return False, f"FFmpeg erro ({proc.returncode}): {err_text[-300:]}"

            if not temp_output.exists() or temp_output.stat().st_size == 0:
                if temp_output.exists():
                    try:
                        temp_output.unlink()
                    except Exception:
                        pass
                return False, "O arquivo temporário de upscaling foi gerado vazio."

            # Substituição segura: o arquivo original só é substituído após término com sucesso
            os.replace(str(temp_output), str(p))
            return True, ""

        except Exception as e:
            if proc and proc.poll() is None:
                proc.kill()
            if temp_output.exists():
                try:
                    temp_output.unlink()
                except Exception:
                    pass
            return False, str(e)


def publish_unique_file(temp_path: pathlib.Path, dest_folder: pathlib.Path, base_stem: str, ext: str) -> pathlib.Path:
    """
    Move atomicamente um arquivo temporário para um nome de arquivo definitivo e único na pasta de destino.
    Se 'Nome.ext' já existir, tenta 'Nome (1).ext', 'Nome (2).ext', etc.
    No Windows, os.rename falha atomicamente (FileExistsError ou WinError 183) se o destino existir,
    garantindo que mesmo downloads concorrentes nunca sobrescrevam um arquivo existente.
    """
    clean_ext = ext.lstrip('.').strip()
    dest_folder = pathlib.Path(dest_folder).resolve()
    base_stem = base_stem.strip() or "video"

    # 1. Tentativa primária: Nome base sem sufixo numérico
    candidate_name = f"{base_stem}.{clean_ext}"
    candidate_path = dest_folder / candidate_name
    try:
        os.rename(str(temp_path), str(candidate_path))
        return candidate_path
    except (FileExistsError, OSError) as e:
        if isinstance(e, FileExistsError) or getattr(e, 'winerror', None) == 183:
            pass
        else:
            raise

    # 2. Tentativas sequenciais: Nome (1).ext, Nome (2).ext, ...
    index = 1
    while True:
        candidate_name = f"{base_stem} ({index}).{clean_ext}"
        candidate_path = dest_folder / candidate_name
        try:
            os.rename(str(temp_path), str(candidate_path))
            return candidate_path
        except (FileExistsError, OSError) as e:
            if isinstance(e, FileExistsError) or getattr(e, 'winerror', None) == 183:
                index += 1
            else:
                raise


def download_video(
    url: str,
    dest_folder: str,
    output_format: str = "mp4",
    video_quality: str = "best",
    audio_quality: str = "best",
    upscale_quality: str = None,
    progress_callback=None,
    is_cancelled=None,
    active_browser=None
):
    """
    Realiza o download e conversão de mídia na URL informada, respeitando a resolução de vídeo
    ou a taxa de bits de áudio selecionada.
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
    op_id = uuid.uuid4().hex[:8]

    def _limpar_arquivos_parciais():
        """Remove arquivos incompletos ou temporários caso o download seja cancelado ou falhe."""
        for f in list(arquivos_rastreados):
            try:
                p = pathlib.Path(str(f))
                if op_id in p.name and p.exists():
                    p.unlink()
            except Exception as e:
                print(f"Aviso: Não foi possível apagar arquivo temporário: {e}")

        try:
            for p in pasta_destino.glob(f"*__tmp_{op_id}*"):
                try:
                    if p.is_file():
                        p.unlink()
                except Exception:
                    pass
        except Exception:
            pass

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
        'outtmpl': str(pasta_destino / f'%(title)s.__tmp_{op_id}.%(ext)s'),
        'quiet': False,
        'no_warnings': False,
        'impersonate': ImpersonateTarget('chrome', '116', 'windows', '10'),
        'color': 'no_color',
        'noplaylist': True,
    }

    # Mescla as opções específicas de vídeo ou áudio e qualidade selecionada
    ydl_opts.update(build_format_options(fmt, video_quality=video_quality, audio_quality=audio_quality))

    # Tenta definir a localização do FFmpeg distribuído. Se for None, o yt-dlp fará fallback no PATH.
    ffmpeg_dir = get_ffmpeg_dir()
    if ffmpeg_dir:
        ydl_opts['ffmpeg_location'] = ffmpeg_dir

    browser = active_browser
    if not browser:
        browser = get_fallback_browser()

    if browser:
        print(f"\nNavegador utilizado para cookies: {browser.capitalize()}")
        ydl_opts['cookiesfrombrowser'] = (browser, None, None, None)
        ydl_opts['logger'] = DownloadLogger(suppress_cookie_errors=True)
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

                # Se for download de vídeo e uma resolução específica foi escolhida, valida existência
                if not is_audio and video_quality and video_quality != 'best':
                    try:
                        req_h = int(str(video_quality).replace('p', ''))
                    except ValueError:
                        req_h = None

                    if req_h:
                        formats = info.get('formats', [])
                        eff_heights = []
                        for f in formats:
                            if f.get('vcodec') != 'none':
                                w = f.get('width') or 0
                                h = f.get('height') or 0
                                eff = w if (h > 0 and w > 0 and h > w) else h
                                if eff > 0:
                                    eff_heights.append(eff)

                        max_h = max(eff_heights) if eff_heights else 0
                        thresholds = {2160: 1800, 1440: 1200, 1080: 900, 720: 600, 480: 400, 360: 300}
                        min_thresh = thresholds.get(req_h, req_h * 0.85)

                        if not any(min_thresh <= h <= req_h + 100 for h in eff_heights):
                            return "erro", f"A resolução {video_quality} não está disponível para este vídeo (máxima disponível: {max_h}p)."

                if is_cancelled and is_cancelled():
                    raise DownloadCancelled("Download interrompido pelo usuário.")

                print("--- Iniciando Download ---")
                ydl.download([url])

                # Localização do arquivo baixado (com o identificador temporário op_id)
                final_file = None
                for f in list(arquivos_rastreados):
                    cand = pathlib.Path(f)
                    if op_id in cand.name and cand.suffix.lower() == f'.{fmt}' and cand.exists() and not cand.name.endswith(('.part', '.temp', '.ytdl')):
                        final_file = cand
                        break

                if not final_file:
                    candidates = [
                        c for c in pasta_destino.glob(f"*__tmp_{op_id}*.{fmt}")
                        if not c.name.endswith(('.part', '.temp', '.ytdl')) and c.is_file()
                    ]
                    if candidates:
                        candidates.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                        final_file = candidates[0]

                if not final_file:
                    candidates = [
                        c for c in pasta_destino.glob(f"*__tmp_{op_id}*")
                        if not c.name.endswith(('.part', '.temp', '.ytdl')) and c.is_file()
                    ]
                    if candidates:
                        candidates.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                        final_file = candidates[0]

                # Processamento pós-download: Upscaling convencional via FFmpeg Lanczos
                if not is_audio and upscale_quality and final_file and final_file.exists():
                    if is_cancelled and is_cancelled():
                        raise DownloadCancelled("Download interrompido pelo usuário.")

                    if progress_callback:
                        progress_callback({
                            'status': 'processing',
                            'action': f"Melhorando resolução para {upscale_quality} (Upscaling FFmpeg Lanczos)..."
                        })

                    sucesso_up, msg_up = upscale_video(
                        final_file,
                        target_res=upscale_quality,
                        ffmpeg_dir=ffmpeg_dir,
                        progress_callback=progress_callback,
                        is_cancelled=is_cancelled
                    )

                    if not sucesso_up:
                        if is_cancelled and is_cancelled():
                            raise DownloadCancelled("Download interrompido pelo usuário.")
                        print(f"\nAviso de Upscaling: {msg_up}")
                        clean_stem = final_file.stem.replace(f'.__tmp_{op_id}', '').strip() or title or 'video'
                        final_ext = final_file.suffix.lstrip('.') or fmt
                        published = publish_unique_file(final_file, pasta_destino, clean_stem, final_ext)
                        return "sucesso", f"Download concluído com sucesso. (Aviso: O upscaling para {upscale_quality} não pôde ser aplicado: {msg_up})"

                # Publicação definitiva com proteção contra sobrescrita e numeração sequencial
                if final_file and final_file.exists():
                    clean_stem = final_file.stem.replace(f'.__tmp_{op_id}', '').strip() or title or 'video'
                    final_ext = final_file.suffix.lstrip('.') or fmt
                    published = publish_unique_file(final_file, pasta_destino, clean_stem, final_ext)
                    print(f"Arquivo final salvo como: {published.name}")

            return "sucesso", ""

        except DownloadCancelled:
            _limpar_arquivos_parciais()
            return "cancelado", "Download cancelado pelo usuário."

        except yt_dlp.utils.DownloadError as e:
            error_msg = str(e).lower()
            if "interrompido pelo usuário" in error_msg or "downloadcancelled" in error_msg:
                _limpar_arquivos_parciais()
                return "cancelado", "Download cancelado pelo usuário."

            if 'cookiesfrombrowser' in ydl_opts and is_cookie_lock_error(error_msg):
                b_name = browser.capitalize() if browser else "Navegador"
                print(f"\nNão foi possível carregar cookies do {b_name} (banco de dados em uso ou protegido).")
                print("Tentando continuar o download sem cookies...")
                del ydl_opts['cookiesfrombrowser']
                if 'logger' in ydl_opts:
                    ydl_opts['logger'].suppress_cookie_errors = False
                continue

            print(f"\nERRO yt-dlp: {e}")

            if ("ffmpeg" in error_msg or "ffprobe" in error_msg) and ("not found" in error_msg or "is not installed" in error_msg or "not recognized" in error_msg):
                return "erro", f"FFmpeg não encontrado. É necessário o executável (local ou no PATH) para converter para {fmt.upper()}."
            elif "ffmpeg" in error_msg or "ffprobe" in error_msg or "postprocessing" in error_msg or "conversion failed" in error_msg:
                return "erro", f"Falha no pós-processamento para {fmt.upper()}. Detalhe: {str(e)}"
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

            if 'cookiesfrombrowser' in ydl_opts and is_cookie_lock_error(error_msg):
                b_name = browser.capitalize() if browser else "Navegador"
                print(f"\nNão foi possível carregar cookies do {b_name} (banco de dados em uso ou protegido).")
                print("Tentando continuar o download sem cookies...")
                del ydl_opts['cookiesfrombrowser']
                if 'logger' in ydl_opts:
                    ydl_opts['logger'].suppress_cookie_errors = False
                continue

            print("\n===== ERRO INESPERADO DIAGNÓSTICO =====")
            print(f"Tipo: {type(e).__name__}")
            print(f"repr: {repr(e)}")
            print(f"str: {str(e)}")
            print("Traceback completo:")
            traceback.print_exc()
            print("=======================================")

            return "erro", "Ocorreu um erro inesperado. Verifique o console."
