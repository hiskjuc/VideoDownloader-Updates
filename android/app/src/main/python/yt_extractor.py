import yt_dlp

def get_metadata(url):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            title = info.get('title', 'Sem título')
            uploader = info.get('uploader', 'Canal Desconhecido')
            duration = info.get('duration')
            if duration is None:
                duration_str = "Desconhecida"
            else:
                duration_str = f"{duration}s"

            return f"Sucesso!\nTítulo: {title}\nCanal: {uploader}\nDuração: {duration_str}"
    except Exception as e:
        return f"Erro do yt-dlp: {str(e)}"