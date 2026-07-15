import os
import json
import gradio as gr
import yt_dlp
from google import genai
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
import moviepy.video.fx.all as vfx

def limpar_json(texto):
    texto = texto.strip()
    if texto.startswith("```"):
        texto = texto.replace("```json", "").replace("```", "").strip()
    return texto

def baixar_video_original(url):
    ydl_opts = {
        'format': 'bestvideo[height<=720]+bestaudio/best', # 720p para processar mais rápido no celular
        'merge_output_format': 'mp4',
        'outtmpl': 'video_original.mp4',
        'overwrites': True
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

def extrair_audio(video_input, audio_output):
    video = VideoFileClip(video_input)
    video.audio.write_audiofile(audio_output, logger=None)
    video.close()

def obter_sugestao_de_corte(client):
    arquivo_subido = client.files.upload(file="audio_completo.mp3")
    prompt = (
        "Analise este áudio e encontre o trecho mais impactante ou viral para o TikTok. "
        "O corte deve durar entre 15 e 30 segundos no máximo. "
        "Você DEVE me responder ESTREITAMENTE no formato JSON abaixo, sem textos adicionais:\n"
        "{\n"
        '  "inicio_segundos": 10.0,\n'
        '  "fim_segundos": 30.0,\n'
        '  "titulo": "Título do corte"\n'
        "}"
    )
    resposta = client.models.generate_content(model="gemini-2.5-flash", contents=[arquivo_subido, prompt])
    client.files.delete(name=arquivo_subido.name)
    return json.loads(limpar_json(resposta.text))

def cortar_e_verticalizar(inicio, fim):
    clip = VideoFileClip("video_original.mp4")
    clip_cortado = clip.subclip(inicio, fim)
    largura, altura = clip_cortado.size
    nova_largura = int(altura * (9 / 16))
    clip_vertical = vfx.crop(clip_cortado, x_center=largura/2, y_center=altura/2, width=nova_largura, height=altura)
    clip_vertical.write_videofile("corte_vertical_puro.mp4", codec="libx264", audio_codec="aac", logger=None)
    clip.close()
    clip_cortado.close()
    clip_vertical.close()

def obter_legendas_da_ia(client):
    extrair_audio("corte_vertical_puro.mp4", "audio_corte.mp3")
    arquivo_subido = client.files.upload(file="audio_corte.mp3")
    prompt = (
        "Transcreva este áudio em português. Divida a fala em pequenos blocos de no máximo "
        "2 palavras para a legenda mudar rápido. "
        "Você DEVE responder ESTREITAMENTE no formato JSON:\n"
        "{\n"
        '  "segments": [\n'
        '    {"text": "FALA GALERA", "start": 0.5, "end": 1.2}\n'
        '  ]\n'
        "}"
    )
    resposta = client.models.generate_content(model="gemini-2.5-flash", contents=[arquivo_subido, prompt])
    client.files.delete(name=arquivo_subido.name)
    return json.loads(limpar_json(resposta.text))["segments"]

def aplicar_legendas_finais(dados_legendas):
    video = VideoFileClip("corte_vertical_puro.mp4")
    largura, altura = video.size
    clipes_de_texto = []
    for item in dados_legendas:
        txt_clip = (TextClip(item["text"].upper(), font="Liberation-Sans-Bold", fontsize=40, color="yellow", stroke_color="black", stroke_width=2, method="label")
                    .set_start(item["start"])
                    .set_end(item["end"])
                    .set_position(('center', altura * 0.70)))
        clipes_de_texto.append(txt_clip)
        
    video_final = CompositeVideoClip([video] + clipes_de_texto)
    video_final.write_videofile("resultado_tiktok.mp4", codec="libx264", audio_codec="aac", temp_audiofile="temp.m4a", remove_temp=True, logger=None)
    video.close()
    video_final.close()

def limpar_arquivos_temporarios():
    for f in ["audio_completo.mp3", "audio_corte.mp3", "corte_vertical_puro.mp4", "video_original.mp4"]:
        if os.path.exists(f):
            try: os.remove(f)
            except: pass

# --- FUNÇÃO PRINCIPAL ---
def processar_tudo(url, api_key):
    if not api_key or not url:
        return None, "Erro: preencha a API Key e a URL!"
    try:
        client = genai.Client(api_key=api_key)
        baixar_video_original(url)
        extrair_audio("video_original.mp4", "audio_completo.mp3")
        corte = obter_sugestao_de_corte(client)
        cortar_e_verticalizar(corte["inicio_segundos"], corte["fim_segundos"])
        legendas = obter_legendas_da_ia(client)
        aplicar_legendas_finais(legendas)
        limpar_arquivos_temporarios()
        return "resultado_tiktok.mp4", f"Sucesso! Corte gerado: '{corte['titulo']}'"
    except Exception as e:
        limpar_arquivos_temporarios()
        return None, f"Erro no processamento: {str(e)}"

# --- INTERFACE GRADIO ---
with gr.Blocks() as demo:
    gr.Markdown("# 🎬 Gerador de Cortes para TikTok com IA")
    with gr.Row():
        with gr.Column():
            api_key_input = gr.Textbox(label="Sua Gemini API Key", type="password", placeholder="Cole sua chave aqui...")
            url_input = gr.Textbox(label="Link do YouTube", placeholder="[https://www.youtube.com/watch?v=](https://www.youtube.com/watch?v=)...")
            btn = gr.Button("Gerar Corte com Legendas! ✨", variant="primary")
        with gr.Column():
            video_output = gr.Video(label="Seu Vídeo Pronto")
            status_output = gr.Textbox(label="Status")

    btn.click(processar_tudo, inputs=[url_input, api_key_input], outputs=[video_output, status_output])

demo.launch()
