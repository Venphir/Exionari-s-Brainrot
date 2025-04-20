import discord
from discord.ext import commands, tasks
from TikTokApi import TikTokApi
import random
import asyncio
import os
from dotenv import load_dotenv

# Cargar variables de entorno desde el archivo .env
dotenv_path = ".env"  # Cambia esto si el archivo .env está en otra ubicación
if not os.path.exists(dotenv_path):
    raise FileNotFoundError(f"No se encontró el archivo .env en la ruta: {dotenv_path}")

load_dotenv(dotenv_path=dotenv_path)

# Configurar los intents necesarios
intents = discord.Intents.default()
intents.message_content = True  # Necesario para leer el contenido de los mensajes

# Configuración del bot de Discord
bot = commands.Bot(command_prefix='_', intents=intents)

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
token = os.getenv('BOT_TOKEN')

if not token:
    raise ValueError("El token del bot no se ha encontrado. Asegúrate de que el archivo .env contiene 'BOT_TOKEN'.")

# Validar el formato del token
if len(token) < 50:  # Los tokens suelen ser largos; ajusta este valor si es necesario
    raise ValueError("El token parece inválido. Verifica que sea correcto.")

bot.run(token)