import os
import re
import time
import streamlit as st
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from youtubesearchpython import VideosSearch
import yt_dlp
import tempfile  
import zipfile   
import shutil    

# ========= CONFIGURAÇÕES SPOTIFY ==========

SPOTIPY_REDIRECT_URI = st.secrets.get("SPOTIPY_REDIRECT_URI", 'http://127.0.0.1:8888/callback')

# ========= FUNÇÕES AUXILIARES ==========

def limpar_nome(nome):
    """Remove caracteres inválidos para nomes de arquivo."""
    return re.sub(r'[\\/*?:"<>|]', "", nome)

def get_playlist_id(url):
    """Extrai o ID da playlist de uma URL do Spotify."""
    try:
        return url.split('/')[-1].split('?')[0]
    except (IndexError, AttributeError):
        return None
    
# ========= FUNÇÕES PRINCIPAIS ==========
@st.cache_resource
def autenticar_spotify():
    "Autentica com a API do Spotify usando Spotipy. Usa cache do Streamlit."
    try:
        auth_manager = SpotifyOAuth(
            client_id=st.secrets["SPOTIPY_CLIENT_ID"],
            client_secret=st.secrets["SPOTIPY_CLIENT_SECRET"],
            redirect_uri=SPOTIPY_REDIRECT_URI,
            scope="playlist-read-private",
            cache_path=".spotipy_cache" 
        )
        return spotipy.Spotify(auth_manager=auth_manager)
    except Exception as e:
        st.error(f"❌ Erro na autenticação do Spotify: {str(e)}")
        st.error("Verifique se as variáveis de ambiente (secrets) `SPOTIPY_CLIENT_ID` e `SPOTIPY_CLIENT_SECRET` estão configuradas corretamente na sua plataforma de hospedagem.")
        st.stop()

@st.cache_data
def get_todas_as_musicas(playlist_id):
    "Busca TODAS as músicas de uma playlist, lidando com paginação."
    try:
        _sp = autenticar_spotify()
        
        resultados = _sp.playlist_items(playlist_id)
        musicas = resultados['items']
        while resultados['next']:
            resultados = _sp.next(resultados)
            musicas.extend(resultados['items'])
        return musicas
    except Exception as e:
        st.error(f"Não foi possível buscar as músicas da playlist. Verifique a URL e suas permissões. Erro: {e}")
        return []

def baixar_musica(nome_musica, artista, pasta_destino, status_placeholder):
    """Busca no YouTube e baixa a música como MP3 usando yt-dlp."""
    nome_arquivo_base = f"{limpar_nome(artista)} - {limpar_nome(nome_musica)}"
    caminho_completo = os.path.join(pasta_destino, nome_arquivo_base)


    try:
        busca = f"{artista} - {nome_musica} official audio"
        status_placeholder.info(f"🔎 Buscando: {busca}...")
        resultado = VideosSearch(busca, limit=1, timeout=10).result()

        if not resultado or not resultado.get('result'):
            status_placeholder.warning(f"⚠️ Não encontrado no YouTube: {busca}")
            return None

        video_url = resultado['result'][0]['link']
        
        status_placeholder.info(f"⬇️ Baixando: {nome_arquivo_base}")

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f"{caminho_completo}.%(ext)s",
            'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
            'quiet': True,
            'noplaylist': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
        
        caminho_final_arquivo = f"{caminho_completo}"

        status_placeholder.success(f"✅ Sucesso: {nome_arquivo_base}")
        return caminho_final_arquivo

    except Exception as e:
        status_placeholder.error(f"❌ Erro ao baixar {nome_arquivo_base}: {str(e)}")
        return None

# ========= LÓGICA DA APLICAÇÃO WEB (STREAMLIT) ==========
st.set_page_config(page_title="Spotify Downloader", page_icon="📻", layout="wide")

st.title("📻 Spotify Playlist Downloader")
st.markdown("Cole a URL de uma playlist do Spotify, e baixe um arquivo `.zip` com todas as músicas em MP3.")

# --- Entradas do Usuário ---
url_playlist = st.text_input(
    "🔗 Cole a URL da playlist do Spotify",
    placeholder="https://open.spotify.com/playlist/..."
)

# A entrada de pasta foi removida (para simplificar o uso, já que o Streamlit não lida bem com caminhos de arquivos locais).
# As opções avançadas foram simplificadas (Simplificado para apenas uma opção, mas vou ver se volto a como era antes).
with st.expander("⚙️ Opções Avançadas"):
    limite_download = st.number_input(
        "🎵 Máximo de músicas a baixar (0 = todas)",
        min_value=0, value=1, step=1, 
    )

if st.button("Iniciar Download", type="primary", use_container_width=True):
    playlist_id = get_playlist_id(url_playlist)
    if not url_playlist or not playlist_id:
        st.error("Por favor, insira uma URL de playlist do Spotify válida.")
    else:
        sp = autenticar_spotify()
        
        with st.spinner("Buscando informações da playlist..."):
            todas_as_musicas = get_todas_as_musicas(playlist_id)
        
        if todas_as_musicas:
            total_playlist = len(todas_as_musicas)
            st.info(f"🎶 Playlist encontrada com {total_playlist} músicas.")

            musicas_a_processar = todas_as_musicas
            if limite_download > 0:
                musicas_a_processar = musicas_a_processar[:limite_download]

            total_a_baixar = len(musicas_a_processar)
            if total_a_baixar == 0:
                st.warning("Nenhuma música para baixar com os critérios definidos.")
            else:
                st.header(f"3. Acompanhando o Progresso (Baixando {total_a_baixar} músicas)")
                
                status_placeholder = st.empty()
                progress_bar = st.progress(0.0)
                
                # Usa um diretório temporário que é automaticamente limpo no final
                with tempfile.TemporaryDirectory() as temp_dir:
                    st.info(f"Criando pasta temporária em: {temp_dir}")

                    for i, item in enumerate(musicas_a_processar):
                        musica = item.get('track')
                        if musica and musica.get('name'):
                            st.markdown(f"--- \n **Música {i + 1}/{total_a_baixar}**")
                            
                            caminho_arquivo_baixado = baixar_musica(
                                musica['name'],
                                musica['artists'][0]['name'],
                                temp_dir,
                                status_placeholder
                            )
                        else:
                            st.warning(f"Item {i+1} da lista não é uma música válida e será pulado.")
                        
                        progress_bar.progress((i + 1) / total_a_baixar)
                        time.sleep(1) # Pequeno delay para legibilidade

                    st.success("✅ Download de faixas individuais concluído! Preparando o arquivo .zip...")

                    # Criar o arquivo Zip
                    nome_playlist_limpo = limpar_nome(sp.playlist(playlist_id)['name'])
                    caminho_zip = os.path.join(temp_dir, f"{nome_playlist_limpo}.zip")
                    
                    with zipfile.ZipFile(caminho_zip, 'w') as zf:
                        for root, _, files in os.walk(temp_dir):
                            for file in files:
                                if file.endswith('.mp3'):
                                    zf.write(os.path.join(root, file), arcname=file)
                    
                    st.success(f"🎉 Arquivo '{nome_playlist_limpo}.zip' pronto para download!")

                    # Oferecer o arquivo .zip para download
                    with open(caminho_zip, "rb") as f:
                        st.download_button(
                            label="Clique aqui para baixar o .zip",
                            data=f,
                            file_name=f"{nome_playlist_limpo}.zip",
                            mime="application/zip",
                            use_container_width=True
                        )

                # A pasta temporária é automaticamente removida aqui
                st.balloons()