import os
import re
import hashlib
import tempfile
import urllib.parse
import requests
from PySide6.QtCore import QThread, Signal

from version import __version__, GITHUB_OWNER, GITHUB_REPO

INSTALLER_FILENAME = "VideoDownloader_Setup.exe"
CHECKSUM_FILENAME = "checksums.txt"

TRUSTED_REDIRECT_HOSTS = {
    "github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
    "github-releases.githubusercontent.com",
    "codeload.github.com",
}

_VERSION_REGEX = re.compile(r"^\d+\.\d+(?:\.\d+)*$")
_SHA256_REGEX = re.compile(r"^[a-fA-F0-9]{64}$")


def parse_version(v_str: str) -> tuple[int, ...]:
    """
    Converte uma string de versão ('1.0.0', 'v1.1.0') em tupla numérica normalizada.
    Lança ValueError para tags vazias, prereleases ('1.0.0-beta') ou formatos inválidos.
    """
    if not isinstance(v_str, str):
        raise ValueError(f"Versão inválida: {v_str!r}")

    clean = v_str.strip()
    if clean.startswith(("v", "V")):
        clean = clean[1:].strip()

    if not clean or not _VERSION_REGEX.match(clean):
        raise ValueError(f"Formato de versão inválido: {v_str!r}")

    parts = [int(p) for p in clean.split(".")]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def is_valid_sha256(digest: str) -> bool:
    return isinstance(digest, str) and bool(_SHA256_REGEX.match(digest.strip()))


def extract_api_sha256(asset: dict) -> str:
    """Extrai o digest SHA-256 fornecido diretamente pelos metadados do asset no GitHub, se existir."""
    raw_digest = asset.get("digest")
    if isinstance(raw_digest, str) and raw_digest.lower().startswith("sha256:"):
        candidate = raw_digest.split(":", 1)[1].strip().lower()
        if is_valid_sha256(candidate):
            return candidate
    return ""


def is_trusted_initial_asset_url(url: str, owner: str, repo: str, expected_filename: str = None) -> bool:
    """Valida se a URL inicial pertence estritamente às releases HTTPS do repositório configurado."""
    if not isinstance(url, str) or not owner or not repo:
        return False

    try:
        parsed = urllib.parse.urlparse(url.strip())
    except Exception:
        return False

    if parsed.scheme != "https" or parsed.username or parsed.password:
        return False

    if (parsed.hostname or "").lower() != "github.com":
        return False

    expected_prefix = f"/{owner.strip().lower()}/{repo.strip().lower()}/releases/download/"
    path_lower = parsed.path.lower()
    if not path_lower.startswith(expected_prefix):
        return False

    if expected_filename and not parsed.path.endswith(f"/{expected_filename}"):
        return False

    return True


def is_trusted_redirect_url(url: str) -> bool:
    """Valida se uma URL de redirecionamento do GitHub utiliza HTTPS e pertence a um host oficial."""
    if not isinstance(url, str):
        return False

    try:
        parsed = urllib.parse.urlparse(url.strip())
    except Exception:
        return False

    if parsed.scheme != "https" or parsed.username or parsed.password:
        return False

    hostname = (parsed.hostname or "").lower()
    return hostname in TRUSTED_REDIRECT_HOSTS


def verify_response_chain(response, owner: str, repo: str, expected_filename: str = None) -> bool:
    """Verifica todos os redirecionamentos e a URL final de uma resposta HTTP."""
    history = getattr(response, "history", None) or []
    for hop in history:
        hop_url = getattr(hop, "url", "")
        if isinstance(hop_url, str) and hop_url:
            if not is_trusted_redirect_url(hop_url):
                return False

    final_url = getattr(response, "url", "")
    if isinstance(final_url, str) and final_url:
        if not is_trusted_redirect_url(final_url):
            return False

    return True


def parse_checksum_manifest(manifest_text: str, target_filename: str = INSTALLER_FILENAME) -> str:
    """
    Procura no manifesto checksums.txt a linha correspondente exatamente a target_filename
    e retorna seu hash SHA-256 validado em minúsculas. Lança ValueError se ausente ou inválido.
    """
    if not isinstance(manifest_text, str):
        raise ValueError("Manifesto de checksums inválido.")

    for raw_line in manifest_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        parts = line.split(None, 1)
        if len(parts) != 2:
            continue

        hash_candidate, filename_candidate = parts[0].strip(), parts[1].strip()
        if filename_candidate.startswith("*"):
            filename_candidate = filename_candidate[1:].strip()

        if filename_candidate == target_filename:
            if not is_valid_sha256(hash_candidate):
                raise ValueError("Hash SHA-256 malformado no manifesto.")
            return hash_candidate.lower()

    raise ValueError(f"Entrada para {target_filename} não encontrada no manifesto de checksums.")


EXCLUDE_SECTION_PATTERNS = [
    r'licen[çc]',
    r'third[- ]party',
    r'terceiros',
    r'gpl',
    r'arquivos\s+dispon[íi]veis',
    r'downloads?',
    r'checksums?',
    r'hashes',
    r'sha-?256',
    r'compila[çc][ãa]o',
    r'build',
    r'desenvolvimento',
    r'instala[çc][ãa]o',
]

PREFERRED_SECTION_PATTERNS = [
    r'o\s+que\s+mudou',
    r'novidades',
    r'mudan[çc]as',
    r'altera[çc][õo]es',
    r'principais',
    r'destaques',
    r"what'?s\s+changed",
    r'changelog',
    r'highlights',
]

TECHNICAL_PATTERNS = [
    r'\b[a-fA-F0-9]{32,64}\b',
    r'checksums\.txt',
    r'_internal\b',
    r'pyinstaller\b',
    r'sys\._meipass\b',
    r'commit\s+[a-f0-9]+',
    r'gplv\d\b',
    r'gnu general public',
    r'gyan\.dev',
    r'inno setup',
]


def clean_markdown_formatting(text: str) -> str:
    """Remove marcadores de formatação Markdown e caracteres decorativos."""
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    text = re.sub(r'[*_]{1,3}([^*_]+)[*_]{1,3}', r'\1', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    text = re.sub(r'^[\s\W\d_]*?[•\-*+]\s*', '', text)
    text = re.sub(r'^[^\w\s-]+\s*', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def parse_items_from_markdown(raw_notes: str) -> list[str]:
    """Extrai itens relevantes de alterações a partir do texto em Markdown da release."""
    text = re.sub(r'```[\s\S]*?```', '', raw_notes)
    text = re.sub(r'<!--[\s\S]*?-->', '', text)

    lines = text.splitlines()

    preferred_items = []
    generic_items = []

    is_preferred_section = False
    is_excluded_section = False

    current_item_lines = []
    current_item_is_preferred = False

    def flush_current_item():
        nonlocal current_item_lines, current_item_is_preferred
        if not current_item_lines:
            return
        full_item_raw = " ".join(current_item_lines).strip()
        current_item_lines = []

        item_text = ""
        match_bold = re.match(r'^\s*[*_]{2}([^*_]+)[*_]{2}[:\s-]*(.*)$', full_item_raw)
        if match_bold:
            header_part = clean_markdown_formatting(match_bold.group(1))
            detail_part = clean_markdown_formatting(match_bold.group(2))

            if any(re.search(pat, header_part, re.IGNORECASE) for pat in TECHNICAL_PATTERNS):
                return

            if len(header_part) >= 6:
                if (detail_part and
                    not any(re.search(pat, detail_part, re.IGNORECASE) for pat in TECHNICAL_PATTERNS) and
                    len(detail_part) <= 90):
                    item_text = f"{header_part}: {detail_part}"
                else:
                    item_text = header_part
        else:
            if any(re.search(pat, full_item_raw, re.IGNORECASE) for pat in TECHNICAL_PATTERNS):
                return
            item_text = clean_markdown_formatting(full_item_raw)

        item_text = re.sub(r'[:\-–—\s]+$', '', item_text).strip()

        if item_text and len(item_text) >= 5:
            if len(item_text) > 160:
                m = re.match(r'^(.{60,150}[.!?])\s', item_text)
                if m:
                    item_text = m.group(1)
                else:
                    item_text = item_text[:140].rsplit(' ', 1)[0] + '...'

            if not item_text.endswith(('.', '!', '?')):
                item_text += '.'

            if current_item_is_preferred:
                preferred_items.append(item_text)
            else:
                generic_items.append(item_text)

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith('#'):
            flush_current_item()
            heading_text = stripped.lstrip('#').strip().lower()

            is_excluded_section = any(re.search(pat, heading_text) for pat in EXCLUDE_SECTION_PATTERNS)
            is_preferred_section = any(re.search(pat, heading_text) for pat in PREFERRED_SECTION_PATTERNS)
            continue

        if is_excluded_section:
            continue

        if stripped.startswith('|') or stripped.endswith('|') or set(stripped) <= {'-', '|', ':', ' '}:
            flush_current_item()
            continue

        match_bullet = re.match(r'^[-*+•]\s+(.*)$', stripped) or re.match(r'^\d+\.\s+(.*)$', stripped)
        if match_bullet:
            flush_current_item()
            current_item_is_preferred = is_preferred_section
            current_item_lines = [match_bullet.group(1).strip()]
        elif current_item_lines and (line.startswith(' ') or line.startswith('\t')):
            current_item_lines.append(stripped)
        elif not current_item_lines and not stripped.startswith('#'):
            clean_para = clean_markdown_formatting(stripped)
            if len(clean_para) >= 15 and not any(re.search(pat, stripped, re.IGNORECASE) for pat in TECHNICAL_PATTERNS):
                if is_preferred_section:
                    current_item_is_preferred = True
                    current_item_lines = [stripped]
                    flush_current_item()
                elif not generic_items and not preferred_items:
                    generic_items.append(clean_para if clean_para.endswith('.') else clean_para + '.')

    flush_current_item()

    return preferred_items if preferred_items else generic_items


def format_release_notes(raw_notes: str, max_items: int = 4, owner: str = "", repo: str = "") -> str:
    """
    Formata o texto bruto das notas de lançamento (Markdown) em um resumo conciso,
    filtrando tabelas, hashes, termos jurídicos e dados técnicos internos.
    """
    fallback = "- Não há um resumo de alterações disponível para esta versão. Consulte as notas completas no GitHub."
    if owner and repo:
        fallback += f"\n\nNotas completas: https://github.com/{owner}/{repo}/releases"

    if not isinstance(raw_notes, str) or not raw_notes.strip():
        return fallback

    items = parse_items_from_markdown(raw_notes)
    if not items:
        return fallback

    selected = items[:max_items]
    return "\n".join(f"- {it}" for it in selected)


class UpdateChecker(QThread):
    """Consulta a última release estável no GitHub em segundo plano."""
    # version, notes, installer_url, checksum_url, api_sha256
    update_available = Signal(str, str, str, str, str)
    no_update = Signal()
    error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        owner = (GITHUB_OWNER or "").strip()
        repo = (GITHUB_REPO or "").strip()

        if not owner or owner == "SEU_USUARIO" or not repo:
            self.error.emit("Repositório de atualizações não configurado.")
            return

        try:
            current_ver = parse_version(__version__)
        except ValueError as e:
            self.error.emit(f"Versão local inválida: {e}")
            return

        api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
        headers = {"Accept": "application/vnd.github+json"}

        try:
            response = requests.get(api_url, headers=headers, timeout=(5, 10))
            try:
                if self._is_cancelled:
                    return
                response.raise_for_status()
                data = response.json()
            finally:
                response.close()

            if not isinstance(data, dict):
                self.error.emit("Resposta inválida da API de atualizações.")
                return

            if data.get("draft") or data.get("prerelease"):
                self.no_update.emit()
                return

            latest_tag = data.get("tag_name", "")
            try:
                remote_ver = parse_version(latest_tag)
            except ValueError:
                self.error.emit(f"Tag de versão inválida publicada na release: {latest_tag!r}")
                return

            if remote_ver <= current_ver:
                self.no_update.emit()
                return

            notes = data.get("body") or "Sem notas de versão disponíveis."
            assets = data.get("assets")
            if not isinstance(assets, list):
                self.error.emit("Lista de arquivos da release é inválida.")
                return

            installer_url = ""
            checksum_url = ""
            api_sha256 = ""

            for asset in assets:
                if not isinstance(asset, dict):
                    continue
                name = asset.get("name")
                dl_url = asset.get("browser_download_url", "")
                if name == INSTALLER_FILENAME:
                    installer_url = dl_url
                    api_sha256 = extract_api_sha256(asset)
                elif name == CHECKSUM_FILENAME:
                    checksum_url = dl_url

            if not installer_url:
                self.error.emit(f"A release {latest_tag} não contém o instalador {INSTALLER_FILENAME}.")
                return

            if not is_trusted_initial_asset_url(installer_url, owner, repo, INSTALLER_FILENAME):
                self.error.emit("A URL do instalador na release não pertence à origem oficial esperada.")
                return

            if not api_sha256:
                if not checksum_url or not is_trusted_initial_asset_url(checksum_url, owner, repo, CHECKSUM_FILENAME):
                    self.error.emit("A release não fornece digest SHA-256 nem manifesto checksums.txt confiável.")
                    return

            if not self._is_cancelled:
                self.update_available.emit(latest_tag, notes, installer_url, checksum_url, api_sha256)

        except requests.exceptions.RequestException as e:
            if not self._is_cancelled:
                self.error.emit(f"Falha de conexão ao verificar atualizações: {e}")
        except Exception as e:
            if not self._is_cancelled:
                self.error.emit(f"Erro ao processar informações de atualização: {e}")


class UpdateDownloader(QThread):
    """Baixa o instalador em arquivo temporário exclusivo e valida seu SHA-256."""
    progress = Signal(int)
    finished_download = Signal(str)
    error = Signal(str)

    def __init__(self, installer_url: str, checksum_url: str, dest_folder: str, expected_digest: str = "", parent=None):
        super().__init__(parent)
        self.installer_url = installer_url
        self.checksum_url = checksum_url
        self.dest_folder = dest_folder
        self.expected_digest = (expected_digest or "").strip().lower()
        self.is_cancelled = False

    def cancel(self):
        self.is_cancelled = True

    @staticmethod
    def _remover_arquivo_seguro(filepath: str):
        if filepath and os.path.exists(filepath):
            try:
                os.remove(filepath)
            except OSError:
                pass

    def _obter_sha256_esperado(self, owner: str, repo: str) -> str:
        if self.expected_digest:
            if not is_valid_sha256(self.expected_digest):
                raise ValueError("O digest SHA-256 informado pela API é inválido.")
            return self.expected_digest

        if not self.checksum_url or not is_trusted_initial_asset_url(self.checksum_url, owner, repo, CHECKSUM_FILENAME):
            raise ValueError("Checksum de segurança não encontrado ou com origem não confiável.")

        resp = requests.get(self.checksum_url, timeout=(5, 10), allow_redirects=True)
        try:
            resp.raise_for_status()
            if not verify_response_chain(resp, owner, repo, CHECKSUM_FILENAME):
                raise ValueError("Redirecionamento não confiável ao buscar manifesto de checksums.")
            return parse_checksum_manifest(resp.text, INSTALLER_FILENAME)
        finally:
            resp.close()

    def run(self):
        owner = (GITHUB_OWNER or "").strip()
        repo = (GITHUB_REPO or "").strip()

        if not is_trusted_initial_asset_url(self.installer_url, owner, repo, INSTALLER_FILENAME):
            self.error.emit("A URL de download do instalador não é confiável.")
            return

        if not os.path.isdir(self.dest_folder):
            self.error.emit("Pasta temporária de download inválida.")
            return

        try:
            expected_sha256 = self._obter_sha256_esperado(owner, repo)
        except Exception as e:
            self.error.emit(f"Não foi possível validar o manifesto de integridade: {e}")
            return

        if self.is_cancelled:
            self.error.emit("Download cancelado pelo usuário.")
            return

        installer_path = ""
        try:
            # Cria um arquivo temporário exclusivo sem sobrescrever arquivos existentes
            fd, installer_path = tempfile.mkstemp(
                prefix="VideoDownloader_Setup_",
                suffix=".exe",
                dir=self.dest_folder
            )
            os.close(fd)

            r = requests.get(self.installer_url, stream=True, timeout=(5, 15), allow_redirects=True)
            try:
                r.raise_for_status()

                if not verify_response_chain(r, owner, repo, INSTALLER_FILENAME):
                    self._remover_arquivo_seguro(installer_path)
                    self.error.emit("Redirecionamento para host não confiável bloqueado.")
                    return

                content_length_hdr = r.headers.get("content-length") if hasattr(r, "headers") and r.headers else None
                total_length = None
                if content_length_hdr is not None:
                    try:
                        total_length = int(content_length_hdr)
                        if total_length <= 0:
                            self._remover_arquivo_seguro(installer_path)
                            self.error.emit("Tamanho de arquivo inválido informado pelo servidor.")
                            return
                    except ValueError:
                        total_length = None

                hasher = hashlib.sha256()
                downloaded_bytes = 0

                with open(installer_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if self.is_cancelled:
                            break
                        if chunk:
                            f.write(chunk)
                            hasher.update(chunk)
                            downloaded_bytes += len(chunk)
                            if total_length:
                                done = min(99, int(100 * downloaded_bytes / total_length))
                                self.progress.emit(done)
                            else:
                                self.progress.emit(0)
            finally:
                r.close()

            if self.is_cancelled:
                self._remover_arquivo_seguro(installer_path)
                self.error.emit("Download cancelado pelo usuário.")
                return

            if downloaded_bytes == 0:
                self._remover_arquivo_seguro(installer_path)
                self.error.emit("O arquivo baixado está vazio.")
                return

            if total_length is not None and downloaded_bytes != total_length:
                self._remover_arquivo_seguro(installer_path)
                self.error.emit(
                    f"Download incompleto: recebidos {downloaded_bytes} de {total_length} bytes."
                )
                return

            local_sha256 = hasher.hexdigest().lower()
            if local_sha256 != expected_sha256:
                self._remover_arquivo_seguro(installer_path)
                self.error.emit(
                    "A verificação de integridade SHA-256 falhou. O instalador foi descartado por segurança."
                )
                return

            self.progress.emit(100)
            self.finished_download.emit(installer_path)

        except requests.exceptions.RequestException as e:
            self._remover_arquivo_seguro(installer_path)
            self.error.emit(f"Erro de rede ao baixar atualização: {e}")
        except Exception as e:
            self._remover_arquivo_seguro(installer_path)
            self.error.emit(f"Falha ao processar o download da atualização: {e}")