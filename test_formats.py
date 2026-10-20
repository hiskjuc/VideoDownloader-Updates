import yt_dlp
from downloader import build_format_options, VIDEO_FORMATS, AUDIO_FORMATS

def run_tests():
    print("Iniciando testes de configuração de formatos...\n")

    # 1. Teste de formato padrão
    default_opts = build_format_options(None)
    assert default_opts['merge_output_format'] == 'mp4', "Padrão deve ser MP4"
    print("[OK] Formato padrão validado como MP4.")

    # 2. Teste de todos os formatos de vídeo
    for v_fmt in ['mp4', 'mkv', 'webm', 'mov', 'avi']:
        opts = build_format_options(v_fmt)
        assert 'bestvideo' in opts['format'], f"Formato {v_fmt} deve buscar vídeo"
        pps = opts.get('postprocessors', [])
        assert any(p['key'] == 'FFmpegVideoConvertor' and p['preferedformat'] == v_fmt for p in pps), \
            f"FFmpegVideoConvertor ausente para {v_fmt}"

        # Valida se o yt_dlp aceita as opções sem erro
        with yt_dlp.YoutubeDL(opts) as ydl:
            assert ydl is not None
        print(f"[OK] Vídeo {v_fmt.upper()}: {opts}")

    # 3. Teste de todos os formatos de áudio
    for a_fmt in ['mp3', 'm4a', 'wav', 'flac', 'opus']:
        opts = build_format_options(a_fmt)
        assert opts['format'] == 'bestaudio/best', f"Formato {a_fmt} deve buscar apenas áudio"
        assert 'merge_output_format' not in opts, f"Áudio {a_fmt} não deve ter merge_output_format"
        pps = opts.get('postprocessors', [])
        assert len(pps) == 1 and pps[0]['key'] == 'FFmpegExtractAudio', f"FFmpegExtractAudio ausente para {a_fmt}"
        assert pps[0]['preferredcodec'] == a_fmt

        if a_fmt == 'mp3':
            assert pps[0].get('preferredquality') == '192', "MP3 deve usar 192 kbps"
        elif a_fmt in ('wav', 'flac'):
            assert 'preferredquality' not in pps[0], f"Formato sem perdas ({a_fmt}) não deve fixar bitrate de MP3"

        with yt_dlp.YoutubeDL(opts) as ydl:
            assert ydl is not None
        print(f"[OK] Áudio {a_fmt.upper()}: {opts}")

    print("\nTodos os testes passaram com sucesso!")

if __name__ == "__main__":
    run_tests()