# -*- mode: python ; coding: utf-8 -*-
import os

block_cipher = None

# Resolve o caminho absoluto do diretório contendo o arquivo .spec
spec_dir = os.path.abspath(SPECPATH)

ff_binaries = []
ffmpeg_path = os.path.join(spec_dir, 'ffmpeg.exe')
ffprobe_path = os.path.join(spec_dir, 'ffprobe.exe')

# Só inclui no empacotamento se ambos os binários estiverem disponíveis no diretório do .spec
if os.path.exists(ffmpeg_path) and os.path.exists(ffprobe_path):
    ff_binaries.append((ffmpeg_path, '.'))
    ff_binaries.append((ffprobe_path, '.'))

extra_datas = []
license_path = os.path.join(spec_dir, 'LICENSE-FFMPEG.txt')
if os.path.exists(license_path):
    extra_datas.append((license_path, '.'))

a = Analysis(
    [os.path.join(spec_dir, 'main.py')],
    pathex=[spec_dir],
    binaries=ff_binaries,
    datas=extra_datas,
    hiddenimports=[
        'yt_dlp',
        'yt_dlp.extractor',
        'yt_dlp.utils',
        'yt_dlp.networking.impersonate',
        'curl_cffi',
        'requests',
        'version',
        'updater',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='VideoDownloader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='VideoDownloader',
)