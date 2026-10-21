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
            duration = info.get('duration', 0)

            return f"Sucesso!\nTítulo: {title}\nCanal: {uploader}\nDuração: {duration}s"
    except Exception as e:
        return f"Erro do yt-dlp: {str(e)}"