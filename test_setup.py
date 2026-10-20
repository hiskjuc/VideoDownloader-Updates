import yt_dlp

def test_yt_dlp_api():
    """Valida se a classe principal do yt-dlp pode ser instanciada."""
    print("Iniciando teste de setup...")
    try:
        # Instancia o YoutubeDL apenas para validar que a API oficial está acessível
        ydl_opts = {'quiet': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            assert ydl is not None

        print("Teste PASSOU: yt_dlp.YoutubeDL foi instanciado com sucesso no Windows.")
    except Exception as e:
        print(f"Teste FALHOU: Ocorreu um erro ao carregar a API do yt-dlp.\nErro: {e}")

if __name__ == "__main__":
    test_yt_dlp_api()