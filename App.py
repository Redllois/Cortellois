import os
import json
import streamlit as st
import yt_dlp
from google import genai
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
import moviepy.video.fx.all as vfx

def limpar_json(texto):
    """Remove marcações de bloco de código markdown que a IA costuma retornar"""
    texto = texto.strip()
    if texto.startswith("```"):
        texto = texto.replace("```json", "").replace("```", "").strip()
    return texto

def baixar_video_original(url):
    """Baixa o vídeo do YouTube em MP4 (resolução máxima de 1080p)"""
    ydl_opts = {
        'format': 'bestvideo[height<=1080]+bestaudio/best',
        'merge_output_format': 'mp4',
        'outtmpl': 'video_original.mp4',
        'overwrites': True
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

def extrair_audio(video_input, audio_output):
    """Extrai a trilha de som do vídeo para economizar banda no envio da IA"""
    video = VideoFileClip(video_input)
    video.audio.write_audiofile(audio_output, logger=None)
    video.close()

def obter_sugestao_de_corte(client):
    """Pede ao Gemini para ouvir o áudio completo e sugerir o melhor trecho de corte"""
    arquivo_subido = client.files.upload(file="audio_completo.mp3")
    
    prompt = (
        "Analise este áudio e encontre o trecho mais impactante, dinâmico ou viral para o TikTok. "
        "O corte deve durar entre 20 e 45 segundos no máximo. "
        "Você DEVE me responder ESTREITAMENTE no formato JSON abaixo, sem textos adicionais antes ou depois:\n"
        "{\n"
        '  "inicio_segundos": 15.0,\n'
        '  "fim_segundos": 45.0,\n'
        '  "titulo": "Título chamativo do corte"\n'
        "}"
    )
    
    resposta = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[arquivo_subido, prompt]
    )
    client.files.delete(name=arquivo_subido.name)
    
    dados = json.loads(limpar_json(resposta.text))
    return dados

def cortar_e_verticalizar(inicio, fmt_fim):
    """Corta o trecho indicado e faz o reenquadramento em 9:16 (vertical)"""
    clip = VideoFileClip("video_original.mp4")
    clip_cortado = clip.subclip(inicio, fmt_fim)
    
    largura, altura = clip_cortado.size
    nova_largura = int(altura * (9 / 16))
    
    clip_vertical = vfx.crop(
        clip_cortado, 
        x_center=largura / 2, 
        y_center=altura / 2, 
        width=nova_largura, 
        height=altura
    )
    
    clip_vertical.write_videofile("corte_vertical_puro.mp4", codec="libx264", audio_codec="aac", logger=None)
    clip.close()
    clip_cortado.close()
    clip_vertical.close()

def obter_legendas_da_ia(client):
    """Extrai o áudio do trecho cortado e pede para o Gemini transcrever com os tempos"""
    extrair_audio("corte_vertical_puro.mp4", "audio_corte.mp3")
    arquivo_subido = client.files.upload(file="audio_corte.mp3")
    
    prompt = (
        "Transcreva este áudio em português. Divida a fala em pequenos blocos de "
        "no máximo 2 palavras para a legenda mudar rapidamente na tela. "
        "Você DEVE responder ESTREITAMENTE no formato JSON:\n"
        "{\n"
        '  "segments": [\n'
        '    {"text": "FALA GALERA", "start": 0.5, "end": 1.2}\n'
        '  ]\n'
        "}"
    )
    
    resposta = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[arquivo_subido, prompt]
    )
    client.files.delete(name=arquivo_subido.name)
    
    dados = json.loads(limpar_json(resposta.text))
    return dados["segments"]

def aplicar_legendas_finais(dados_legendas):
    """Queima as legendas amarelas com borda preta por cima do vídeo vertical"""
    video = VideoFileClip("corte_vertical_puro.mp4")
    largura, altura = video.size
    
    clipes_de_texto = []
    for item in dados_legendas:
        texto = item["text"].upper()
        inicio = item["start"]
        fim = item["end"]
        
        txt_clip = (TextClip(
                        texto, 
                        font="Liberation-Sans-Bold", 
                        fontsize=40, 
                        color="yellow", 
                        stroke_color="black", 
                        stroke_width=2,
                        method="label"
                    )
                    .set_start(inicio)
                    .set_end(fim)
                    .set_position(('center', altura * 0.65)))
        
        clipes_de_texto.append(txt_clip)
        
    video_final = CompositeVideoClip([video] + clipes_de_texto)
    video_final.write_videofile(
        "resultado_tiktok.mp4",
        codec="libx264",
        audio_codec="aac",
        temp_audiofile="temp_final.m4a",
        remove_temp=True,
        logger=None
    )
    video.close()
    video_final.close()

def limpar_arquivos_temporarios():
    """Remove os arquivos de trabalho para liberar espaço em disco"""
    arquivos = ["audio_completo.mp3", "audio_corte.mp3", "corte_vertical_puro.mp4", "video_original.mp4"]
    for arquivo in arquivos:
        if os.path.exists(arquivo):
            try:
                os.remove(arquivo)
            except:
                pass

# --- INTERFACE WEB (STREAMLIT) ---
st.set_page_config(page_title="Gerador de Cortes IA 🎬", layout="centered")
st.title("Cortador de Vídeos Inteligente 🚀")
st.markdown("Cole o link do YouTube e deixe a nossa IA encontrar, cortar e legendar o melhor trecho!")

st.sidebar.header("Configuração")
api_key_default = os.environ.get("GEMINI_API_KEY", "")
api_key = st.sidebar.text_input("Sua Gemini API Key:", value=api_key_default, type="password")

url_video = st.text_input("URL do Vídeo do YouTube:", placeholder="[https://www.youtube.com/watch?v=](https://www.youtube.com/watch?v=)...")
botao_gerar = st.button("Gerar meu Corte Vertical! ✨", disabled=not api_key)

if botao_gerar and url_video:
    if not api_key:
        st.error("Insira sua Gemini API Key na barra lateral para começar!")
    else:
        try:
            client = genai.Client(api_key=api_key)
            
            with st.status("Processando seu vídeo... Isso pode levar de 1 a 3 minutos.", expanded=True) as status:
                st.write("📥 1. Baixando vídeo original...")
                baixar_video_original(url_video)
                
                st.write("🎵 2. Extraindo áudio para a IA...")
                extrair_audio("video_original.mp4", "audio_completo.mp3")
                
                st.write("🧠 3. IA escolhendo o momento mais viral...")
                corte = obter_sugestao_de_corte(client)
                
                st.write(f"✂️ 4. Cortando trecho: *{corte['titulo']}*...")
                cortar_e_verticalizar(corte["inicio_segundos"], corte["fim_segundos"])
                
                st.write("✍️ 5. Transcrevendo falas em pequenos blocos...")
                legendas = obter_legendas_da_ia(client)
                
                st.write("🎨 6. Aplicando legendas estilo TikTok...")
                aplicar_legendas_finais(legendas)
                
                st.write("🧹 7. Limpando rascunhos...")
                limpar_arquivos_temporarios()
                
                status.update(label="🎉 Seu corte está pronto!", state="complete")
                
            st.success(f"Corte gerado com sucesso: **{corte['titulo']}**!")
            
            if os.path.exists("resultado_tiktok.mp4"):
                st.video("resultado_tiktok.mp4")
                with open("resultado_tiktok.mp4", "rb") as f:
                    st.download_button("📥 Baixar Vídeo para o TikTok", data=f, file_name="corte_tiktok.mp4", mime="video/mp4")
                    
        except Exception as e:
            st.error(f"Erro no pipeline: {e}")
            limpar_arquivos_temporarios()
