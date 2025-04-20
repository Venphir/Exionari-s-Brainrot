import discord
from discord.ext import commands, tasks
from TikTokApi import TikTokApi
import random
import asyncio
import os
from dotenv import load_dotenv

# Cargar variables de entorno desde el archivo .env
load_dotenv()

# Configuración del bot de Discord
bot = commands.Bot(command_prefix='_')

# Configuración de la API de TikTok
api = TikTokApi()

# Lista para almacenar los temas asignados
themes = []

# Comando para asignar temas (hashtags)
@bot.command(name='asignar_tema')
async def assign_theme(ctx, *args):
    global themes
    themes = list(set(args))  # Eliminar duplicados
    await ctx.send(f'Temas asignados: {", ".join(themes)}')

# Tarea periódica para enviar videos aleatorios
@tasks.loop(hours=1)  # Cambia el intervalo si lo deseas (ej. minutes=30)
async def send_random_video():
    if not themes:
        return  # No hay temas asignados

    # Seleccionar un tema aleatorio
    theme = random.choice(themes)

    try:
        # Obtener videos de TikTok por hashtag
        videos = api.by_hashtag(theme.lstrip('#'), count=10)
        if not videos:
            return  # No se encontraron videos

        # Seleccionar un video aleatorio
        video = random.choice(videos)
        video_url = f"https://www.tiktok.com/@{video['author']['uniqueId']}/video/{video['id']}"

        # Enviar el enlace al canal
        channel = bot.get_channel(1363398384890941611)  # ID del canal especificado
        await channel.send(f"Aquí tienes un video de {theme}: {video_url}")

    except Exception as e:
        print(f"Error al obtener videos: {e}")

# Evento cuando el bot está listo
@bot.event
async def on_ready():
    print(f'Bot conectado como {bot.user}')
    send_random_video.start()  # Iniciar la tarea periódica

# Cargar el token desde el archivo .env
bot.run(os.getenv('BOT_TOKEN'))