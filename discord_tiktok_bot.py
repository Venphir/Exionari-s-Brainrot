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
try:
    api = TikTokApi.get_instance(use_test_endpoints=True)  # Usa endpoints de prueba si es necesario
except Exception as e:
    print(f"Error al inicializar TikTokApi: {e}")
    api = None

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
        print("No hay temas asignados. La tarea no se ejecutará.")
        return  # No hay temas asignados

    # Seleccionar un tema aleatorio
    theme = random.choice(themes)
    print(f"Seleccionado tema: {theme}")

    try:
        # Validar conexión con TikTokApi
        if not api:
            print("Error: TikTokApi no está configurada correctamente.")
            return

        # Obtener videos de TikTok por hashtag
        try:
            videos = api.by_hashtag(theme.lstrip('#'), count=10)
        except Exception as e:
            print(f"Error al obtener videos de TikTok: {e}")
            return

        if not videos:
            print(f"No se encontraron videos para el tema: {theme}")
            return  # No se encontraron videos

        # Seleccionar un video aleatorio
        video = random.choice(videos)
        video_url = f"https://www.tiktok.com/@{video['author']['uniqueId']}/video/{video['id']}"
        print(f"Video seleccionado: {video_url}")

        # Enviar el enlace al canal
        channel = bot.get_channel(1363398384890941611)  # ID del canal especificado
        if channel is None:
            print("Error: No se pudo encontrar el canal. Verifica el ID del canal.")
            return

        # Verificar permisos del bot en el canal
        permissions = channel.permissions_for(channel.guild.me)
        if not permissions.send_messages:
            print("Error: El bot no tiene permisos para enviar mensajes en este canal.")
            return
        if not permissions.embed_links:
            print("Advertencia: El bot no tiene permisos para incluir enlaces embebidos. El mensaje puede no mostrarse correctamente.")

        await channel.send(f"Aquí tienes un video de {theme}: {video_url}")

    except discord.Forbidden:
        print("Error: El bot no tiene los permisos necesarios para realizar esta acción.")
    except KeyError as e:
        print(f"Error al procesar datos del video: {e}")
    except Exception as e:
        print(f"Error al obtener o enviar videos: {e}")

# Evento cuando el bot está listo
@bot.event
async def on_ready():
    print(f'Bot conectado como {bot.user}')
    try:
        # Validar que el bot tiene acceso al canal
        channel = bot.get_channel(1363398384890941611)
        if channel is None:
            print("Error: No se pudo encontrar el canal. Verifica el ID del canal.")
        else:
            print(f"El bot tiene acceso al canal: {channel.name}")

            # Verificar permisos del bot en el canal
            permissions = channel.permissions_for(channel.guild.me)
            if not permissions.send_messages:
                print("Error: El bot no tiene permisos para enviar mensajes en este canal.")
            if not permissions.embed_links:
                print("Advertencia: El bot no tiene permisos para incluir enlaces embebidos.")

        send_random_video.start()  # Iniciar la tarea periódica
    except Exception as e:
        print(f"Error al iniciar la tarea periódica: {e}")

# Cargar el token desde el archivo .env
token = os.getenv('BOT_TOKEN')

if not token:
    raise ValueError("El token del bot no se ha encontrado. Asegúrate de que el archivo .env contiene 'BOT_TOKEN'.")

# Validar el formato del token
if len(token) < 50:  # Los tokens suelen ser largos; ajusta este valor si es necesario
    raise ValueError("El token parece inválido. Verifica que sea correcto.")

bot.run(token)