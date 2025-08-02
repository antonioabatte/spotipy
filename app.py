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

# ========= CONFIGURAÇÕES SPOTIFY ==========
# Os valores são carregados dos 'secrets' do Streamlit
CLIENT_ID = st.secrets["SPOTIPY_CLIENT_ID"]
CLIENT_SECRET = st.secrets["SPOTIPY_CLIENT_SECRET"]
REDIRECT_URI = st.secrets["SPOTIPY_REDIRECT_URI"]

# ========= FUNÇÕES AUXILIARES (sem alterações) ==========
def limpar_nome(nome):
    """Remove caracteres inválidos para nomes de arquivo."""
    return re.sub(r'[\\/*?:"<>|]', "", nome)

def get_playlist_id(url):
    """Extrai o ID da playlist de uma URL do Spotify."""
    try:
        return url.split('/')[-1].split('?')[0]
    except (IndexError, AttributeError):
        return None

# ========= FUNÇÕES DE AUTENTICAÇÃO (NOVA ESTRUTURA) ==========

@st.cache_resource
def get_auth_manager():
    """
    Cria e armazena em cache o gerenciador de autenticação do Spotipy.
    Este objeto contém a configuração, mas não o token do usuário.
    É seguro usar cache aqui, pois ele não muda.
    """
    return SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope="playlist-read-private",
        cache_path=None 
    )

def get_spotify_client():
    """
    Gerencia o fluxo de autenticação e retorna um cliente Spotipy autenticado.
    Usa st.session_state para armazenar o token de forma segura entre os reruns.
    """
    auth_manager = get_auth_manager()

    # 1. Tenta obter o token do estado da sessão
    if 'token_info' not in st.session_state:
        # 2. Se não houver token, verifica se há um código de autorização na URL
        try:
            code = st.query_params['code']
        except:
            st.error("Erro: Não foi possível obter o código de autorização da URL.")
            st.stop()
        
        # 3. Se houver um código, troca-o por um token e armazena no estado da sessão
        if code:
            token_info = auth_manager.get_access_token(code, as_dict=True)
            st.session_state['token_info'] = token_info
            # Limpa o código da URL para evitar problemas em recarregamentos
            st.query_params.clear() 
        else:
            st.error("Fluxo de autenticação interrompido. Nenhum código encontrado.")
            st.stop()

    # 4. Verifica se o token armazenado expirou
    token_info = st.session_state['token_info']
    if auth_manager.is_token_expired(token_info):
        refreshed_token_info = auth_manager.refresh_access_token(token_info['refresh_token'])
        st.session_state['token_info'] = refreshed_token_info
        token_info = refreshed_token_info

    # 5. Cria e retorna o cliente Spotipy com o token de acesso válido
    return spotipy.Spotify(auth=token_info['access_token'])

def show_login_page():
    """
    Mostra a página de login para o usuário iniciar o processo.
    """
    auth_manager = get_auth_manager()
    auth_url = auth_manager.get_authorize_url()
    
    st.title("Bem-vindo ao Spotify Downloader!")
    st.write("Para continuar, você precisa autorizar o acesso à sua conta do Spotify.")
    st.link_button("Fazer Login com Spotify", auth_url, use_container_width=True, type="primary")

# ========= FUNÇÕES PRINCIPAIS ==========

@st.cache_data
def get_todas_as_musicas(_sp, playlist_id):
    """Busca TODAS as músicas de uma playlist, lidando com paginação."""
    try:
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
        
        caminho_final_arquivo = f"{caminho_completo}.mp3"
        status_placeholder.success(f"✅ Sucesso: {nome_arquivo_base}")
        return caminho_final_arquivo

    except Exception as e:
        status_placeholder.error(f"❌ Erro ao baixar {nome_arquivo_base}: {str(e)}")
        return None

# ========= LÓGICA DA APLICAÇÃO WEB (ESTRUTURA PRINCIPAL) ==========
st.set_page_config(page_title="Spotify Downloader", page_icon="📻", layout="wide")

# --- FLUXO PRINCIPAL ---
# 1. Se não houver 'code' na URL, o usuário não está logado. Mostra a página de login.
if 'code' not in st.query_params:
    show_login_page()
    st.stop() # Interrompe a execução até o usuário fazer login e ser redirecionado.

# 2. Se houver 'code', significa que o usuário foi redirecionado pelo Spotify.
#    A função get_spotify_client() cuidará da obtenção e armazenamento do token.
try:
    sp = get_spotify_client()
except Exception as e:
    st.error(f"Ocorreu um erro durante a autenticação: {e}")
    st.stop()


# 3. Se chegamos aqui, o login foi bem-sucedido e temos um cliente 'sp'.
st.title("📻 Spotify Playlist Downloader")
st.markdown("Cole a URL de uma playlist do Spotify, e baixe um arquivo `.zip` com todas as músicas em MP3.")
st.success("✅ Login no Spotify realizado com sucesso!")

url_playlist = st.text_input("🔗 Cole a URL da playlist do Spotify", placeholder="https://open.spotify.com/playlist/...")

with st.expander("⚙️ Opções Avançadas"):
    limite_download = st.number_input(
        "🎵 Máximo de músicas a baixar (0 = todas)",
        min_value=0, value=10, step=1,
        help="Se 0, tentará baixar todas as músicas da playlist."
    )

if st.button("Iniciar Download", type="primary", use_container_width=True):
    playlist_id = get_playlist_id(url_playlist)
    if not url_playlist or not playlist_id:
        st.error("Por favor, insira uma URL de playlist do Spotify válida.")
    else:
        with st.spinner("Buscando informações da playlist..."):
            todas_as_musicas = get_todas_as_musicas(sp, playlist_id)
        
        if todas_as_musicas:
            total_playlist = len(todas_as_musicas)
            st.info(f"🎶 Playlist encontrada com {total_playlist} músicas.")

            musicas_a_processar = todas_as_musicas
            if limite_download > 0:
                musicas_a_processar = musicas_a_processar[:limite_download]

            total_a_baixar = len(musicas_a_processar)
            if total_a_baixar > 0:
                st.header(f"Progresso (Baixando {total_a_baixar} músicas)")
                status_placeholder = st.empty()
                progress_bar = st.progress(0.0)
                
                with tempfile.TemporaryDirectory() as temp_dir:
                    arquivos_baixados = []
                    for i, item in enumerate(musicas_a_processar):
                        musica = item.get('track')
                        if musica and musica.get('name'):
                            st.markdown(f"--- \n **Música {i + 1}/{total_a_baixar}**")
                            caminho = baixar_musica(musica['name'], musica['artists'][0]['name'], temp_dir, status_placeholder)
                            if caminho:
                                arquivos_baixados.append(caminho)
                        else:
                            st.warning(f"Item {i+1} pulado (não é uma música válida).")
                        
                        progress_bar.progress((i + 1) / total_a_baixar)
                        time.sleep(0.5)

                    if not arquivos_baixados:
                        st.error("Nenhum arquivo foi baixado com sucesso. Não é possível criar o arquivo .zip.")
                    else:
                        st.success("✅ Download de faixas concluído! Preparando o arquivo .zip...")
                        nome_playlist = limpar_nome(sp.playlist(playlist_id)['name'])
                        caminho_zip = os.path.join(temp_dir, f"{nome_playlist}.zip")
                        
                        with zipfile.ZipFile(caminho_zip, 'w') as zf:
                            for arquivo_mp3 in arquivos_baixados:
                                zf.write(arquivo_mp3, arcname=os.path.basename(arquivo_mp3))
                        
                        st.success(f"🎉 Arquivo '{nome_playlist}.zip' pronto!")
                        with open(caminho_zip, "rb") as f:
                            st.download_button(
                                label="Clique aqui para baixar o .zip",
                                data=f,
                                file_name=f"{nome_playlist}.zip",
                                mime="application/zip",
                                use_container_width=True
                            )
                        st.balloons()