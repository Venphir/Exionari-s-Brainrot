# Standard library imports
import os
import json
import time
import random
import pickle
import asyncio
import traceback
import sys

# Third-party imports
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
import requests as http_requests

# Verificación de dependencias requeridas
try:
    from PIL import Image
except ImportError:
    print("=== ERROR: Pillow no está instalado ===")
    print("Instagrapi requiere Pillow (PIL) para funcionar.")
    print("Ejecuta este comando para instalar la dependencia:")
    print("pip install Pillow>=8.1.1")
    print("=========================================")
    sys.exit(1)

try:
    import instagrapi
    import instagrapi.exceptions
    from instagrapi import Client
except ImportError as e:
    print(f"=== ERROR: No se pudo importar instagrapi ===")
    print(f"Error: {str(e)}")
    print("Ejecuta este comando para instalar la dependencia:")
    print("pip install instagrapi")
    print("==========================================")
    sys.exit(1)

# Cargar variables de entorno desde el archivo .env
dotenv_path = ".env"
if not os.path.exists(dotenv_path):
    raise FileNotFoundError(f"No se encontró el archivo .env en la ruta: {dotenv_path}")

load_dotenv(dotenv_path=dotenv_path)

# Directorio para almacenamiento de caché de videos
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "video_cache")
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

# Registro de videos por tema
THEME_VIDEO_REGISTRY = os.path.join(CACHE_DIR, "theme_videos.pkl")
theme_video_registry = {}
try:
    if os.path.exists(THEME_VIDEO_REGISTRY):
        with open(THEME_VIDEO_REGISTRY, "rb") as f:
            theme_video_registry = pickle.load(f)
except Exception as e:
    print(f"Error al cargar el registro de videos: {e}")
    theme_video_registry = {}

# Configurar los intents necesarios
intents = discord.Intents.default()
intents.message_content = True

# Configuración del bot de Discord
bot = commands.Bot(command_prefix='_', intents=intents, help_command=None)

# Rutas de los archivos
themes_file = "themes.json"
config_file = "config.json"
channels_file = "channels.json"

# Estrategia para evitar comandos duplicados
message_timestamps = {}

# Lista para almacenar los últimos videos enviados (para evitar repeticiones)
recently_sent_videos = []

# Cargar credenciales de Instagram
INSTAGRAM_USERNAME = os.getenv("INSTAGRAM_USERNAME")
INSTAGRAM_PASSWORD = os.getenv("INSTAGRAM_PASSWORD")

if not INSTAGRAM_USERNAME or not INSTAGRAM_PASSWORD:
    raise ValueError("Las credenciales de Instagram no se encontraron en el archivo .env. Asegúrate de incluir 'INSTAGRAM_USERNAME' y 'INSTAGRAM_PASSWORD'.")

# Directorio para almacenar la sesión de Instagram
SESSION_FILE = os.path.join(CACHE_DIR, "instagram_session.json")

# Inicializar el cliente de Instagram
ig_client = Client()
instagram_connected = False

# Cargar token de Discord desde variables de entorno
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("El token del bot de Discord no se encontró en el archivo .env. Asegúrate de incluir 'BOT_TOKEN'.")

# Diccionario para almacenar las tareas de envío por canal
channel_tasks = {}

# Función para transformar el enlace de Instagram a instagramez.com
def transform_to_embedez_url(instagram_url):
    """Transforma un enlace de Instagram a un enlace de instagramez.com."""
    if "instagram.com/reel/" not in instagram_url:
        print(f"[transform_to_embedez_url] URL inválida, no es un enlace de Instagram Reel: {instagram_url}")
        return None
    reel_code = instagram_url.split("reel/")[1].rstrip("/")
    embedez_url = f"https://www.instagramez.com/reel/{reel_code}/"
    print(f"[transform_to_embedez_url] URL transformada: {embedez_url}")
    return embedez_url

# Función para cargar la configuración del intervalo
def load_config():
    if os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
                print(f"Configuración cargada: {config}")
                return config
        except json.JSONDecodeError:
            print("Error: El archivo config.json está corrupto. Usando configuración predeterminada.")
            return {"interval": 5, "unit": "minutes"}
        except Exception as e:
            print(f"Error al cargar la configuración desde el archivo: {e}")
            return {"interval": 5, "unit": "minutes"}
    else:
        print("No se encontró config.json. Usando configuración predeterminada.")
        return {"interval": 5, "unit": "minutes"}

# Función para guardar la configuración del intervalo
def save_config(config):
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=4)
    print("Configuración guardada correctamente.")

# Cargar la configuración inicial
config = load_config()

# Convertir el intervalo a segundos para la tarea
def get_interval_in_seconds(interval, unit):
    if unit == "minutes":
        return interval * 60
    elif unit == "hours":
        return interval * 3600
    elif unit == "days":
        return interval * 86400
    else:
        raise ValueError(f"Unidad de tiempo no válida: {unit}")

# Función para cargar la lista de canales
def load_channels():
    if os.path.exists(channels_file):
        try:
            with open(channels_file, "r", encoding="utf-8") as f:
                channels = json.load(f)
                print(f"Canales cargados: {channels}")
                # Convertir lista antigua de IDs a la nueva estructura si es necesario
                if channels and isinstance(channels[0], int):
                    # Convertir formato antiguo (solo IDs) a nuevo formato
                    channels = [{"channel_id": channel_id, "interval": config["interval"], "unit": config["unit"]} for channel_id in channels]
                    save_channels(channels)  # Guardar en el nuevo formato
                return channels
        except json.JSONDecodeError:
            print("Error: El archivo channels.json está corrupto. Usando lista vacía.")
            return []
        except Exception as e:
            print(f"Error al cargar los canales desde el archivo: {e}")
            return []
    else:
        print("No se encontró channels.json. Usando lista vacía.")
        return []

# Función para guardar la lista de canales
def save_channels(channels):
    with open(channels_file, "w", encoding="utf-8") as f:
        json.dump(channels, f, ensure_ascii=False, indent=4)
    print("Canales guardados correctamente.")

# Lista para almacenar los canales con intervalos
channels = load_channels()

# Evento cuando el bot está listo
@bot.event
async def on_ready():
    print(f'Bot conectado como {bot.user}')
    try:
        await bot.tree.sync()
        print("Comandos de aplicación sincronizados.")
        
        # Iniciar las tareas
        start_channel_tasks()
        clean_timestamps.start()
        clean_recent_videos.start()
        
        bot.loop.create_task(connect_to_instagram())
        
    except Exception as e:
        print(f"Error al inicializar el bot: {e}")
        traceback.print_exc()

# Conectar a Instagram de manera asíncrona
async def connect_to_instagram():
    global ig_client, instagram_connected
    try:
        print("Conectando a Instagram en segundo plano...")
        await bot.loop.run_in_executor(None, login_with_session)
        instagram_connected = True
        print("✅ Conexión a Instagram completada en segundo plano.")
    except Exception as e:
        print(f"❌ Error al conectar con Instagram: {e}")
        traceback.print_exc()
        instagram_connected = False

# Función para cargar o iniciar una nueva sesión
def login_with_session():
    if os.path.exists(SESSION_FILE):
        try:
            ig_client.load_settings(SESSION_FILE)
            ig_client.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
            print("Sesión cargada exitosamente desde el archivo.")
            return
        except Exception as e:
            print(f"Error al cargar la sesión: {e}. Iniciando una nueva sesión...")

    try:
        ig_client.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
        print("Conexión a Instagram exitosa.")
    except instagrapi.exceptions.TwoFactorRequired:
        print("Se requiere autenticación de dos factores (2FA).")
        print(f"Se ha enviado un código de verificación a tu método de 2FA configurado para {INSTAGRAM_USERNAME}.")
        verification_code = input("Por favor, introduce el código de verificación: ")
        try:
            ig_client.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD, verification_code=verification_code)
            print("Conexión a Instagram exitosa con 2FA.")
        except Exception as e:
            print(f"Error al iniciar sesión con 2FA: {e}")
            raise
    except Exception as e:
        print(f"Error al iniciar sesión en Instagram: {e}")
        raise

    try:
        ig_client.dump_settings(SESSION_FILE)
        print("Sesión guardada exitosamente.")
    except Exception as e:
        print(f"Error al guardar la sesión: {e}")

# Llamar a la función de inicio de sesión
login_with_session()

# Función para cargar los temas desde el archivo
def load_themes():
    global themes
    if os.path.exists(themes_file):
        try:
            with open(themes_file, "r", encoding="utf-8") as f:
                themes = json.load(f)
                print(f"Temas cargados: {themes}")
        except json.JSONDecodeError:
            print("Error: El archivo themes.json está corrupto. Se reiniciará la lista de temas.")
            themes = []
        except Exception as e:
            print(f"Error al cargar los temas desde el archivo: {e}")
            themes = []
    else:
        themes = []

# Función para guardar los temas en el archivo
def save_themes():
    with open(themes_file, "w", encoding="utf-8") as f:
        json.dump(themes, f, ensure_ascii=False, indent=4)
    print("Temas guardados correctamente.")

# Lista para almacenar los temas asignados
themes = []
load_themes()

# Función para validar si un enlace de Instagram es accesible
async def is_valid_instagram_url(url):
    """Verifica si un enlace de Instagram es válido y accesible."""
    if "instagram.com" not in url:
        print(f"[is_valid_instagram_url] URL no pertenece a Instagram: {url}")
        return False
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    try:
        response = http_requests.head(url, headers=headers, timeout=5, allow_redirects=True)
        if response.status_code == 405 or response.status_code == 403:
            response = http_requests.get(url, headers=headers, timeout=5, allow_redirects=True, stream=True)
        if response.status_code == 200:
            if "This post is not available" in response.text or "post unavailable" in response.text.lower():
                print(f"[is_valid_instagram_url] Reel no disponible: {url}")
                return False
            print(f"[is_valid_instagram_url] URL válida: {url}")
            return True
        print(f"[is_valid_instagram_url] Código de estado no válido ({response.status_code}): {url}")
        return False
    except (http_requests.exceptions.RequestException, http_requests.exceptions.Timeout) as e:
        print(f"[is_valid_instagram_url] Error al verificar URL: {url}, Error: {e}")
        return False

# Función para buscar Instagram Reels por hashtag
async def get_instagram_reels_by_hashtag(hashtag, count=5, use_cache=True, force_refresh=False):
    global theme_video_registry
    print(f"[get_instagram_reels_by_hashtag] Buscando Instagram Reels para hashtag: {hashtag}")
    hashtag_clean = hashtag.lstrip('#').lower()
    videos_info = []

    if use_cache and hashtag_clean in theme_video_registry and not force_refresh:
        cached_videos = theme_video_registry.get(hashtag_clean, [])
        print(f"[get_instagram_reels_by_hashtag] Encontrados {len(cached_videos)} videos en caché para {hashtag_clean}")
        valid_videos = []
        for video in cached_videos:
            if "instagram.com" not in video['url']:
                print(f"[get_instagram_reels_by_hashtag] Eliminando URL no válida del caché: {video['url']}")
                continue
            if await is_valid_instagram_url(video['url']):
                valid_videos.append(video)
            else:
                print(f"[get_instagram_reels_by_hashtag] Enlace no válido eliminado del caché: {video['url']}")
        
        if valid_videos:
            random.shuffle(valid_videos)
            videos_info = valid_videos[:count]
            theme_video_registry[hashtag_clean] = valid_videos
            try:
                with open(THEME_VIDEO_REGISTRY, "wb") as f:
                    pickle.dump(theme_video_registry, f)
                print(f"[get_instagram_reels_by_hashtag] Caché actualizado para '{hashtag_clean}'")
            except Exception as e:
                print(f"[get_instagram_reels_by_hashtag] Error al actualizar caché: {e}")

    if len(videos_info) < count or force_refresh:
        print(f"[get_instagram_reels_by_hashtag] Buscando nuevos Reels en Instagram para {hashtag_clean}")
        try:
            try:
                ig_client.get_timeline_feed()
            except Exception as e:
                print(f"[get_instagram_reels_by_hashtag] Sesión inválida: {e}. Reconectando...")
                login_with_session()

            hashtag_data = ig_client.hashtag_info(hashtag_clean)
            if not hashtag_data:
                print(f"[get_instagram_reels_by_hashtag] No se encontró el hashtag: {hashtag_clean}")
                return videos_info

            medias = ig_client.hashtag_medias_recent(hashtag_clean, amount=20)
            print(f"[get_instagram_reels_by_hashtag] Encontrados {len(medias)} medios recientes para {hashtag_clean}")
            temp_videos = []
            for media in medias:
                if media.media_type == 2:  # 2 indica un video (Reel)
                    video_url = f"https://www.instagram.com/reel/{media.code}/"
                    temp_videos.append({
                        'id': media.pk,
                        'url': video_url,
                        'title': media.caption_text[:100] if media.caption_text else f'Reel de {media.user.username}',
                        'uploader': media.user.username
                    })

            new_videos = []
            for video in temp_videos:
                if await is_valid_instagram_url(video['url']):
                    new_videos.append(video)

            if not force_refresh and hashtag_clean in theme_video_registry:
                existing_videos = theme_video_registry[hashtag_clean]
                all_videos = new_videos + [v for v in existing_videos if v not in new_videos]
            else:
                all_videos = new_videos

            random.shuffle(all_videos)
            videos_info = all_videos[:count]

            if all_videos and use_cache:
                theme_video_registry[hashtag_clean] = all_videos[:50]
                try:
                    with open(THEME_VIDEO_REGISTRY, "wb") as f:
                        pickle.dump(theme_video_registry, f)
                    print(f"[get_instagram_reels_by_hashtag] Reels para '{hashtag_clean}' agregados a caché")
                except Exception as e:
                    print(f"[get_instagram_reels_by_hashtag] Error al guardar caché: {e}")
        except Exception as e:
            print(f"[get_instagram_reels_by_hashtag] Error al buscar Reels: {e}")
            traceback.print_exc()

    print(f"[get_instagram_reels_by_hashtag] Total de videos devueltos: {len(videos_info)}")
    return videos_info[:count]

# Función para enviar videos a un canal específico
async def send_video_to_channel(channel_id):
    global themes, instagram_connected, recently_sent_videos
    if not themes or not instagram_connected:
        print(f"[send_video_to_channel] No se puede ejecutar para canal {channel_id}: faltan temas o conexión a Instagram.")
        return

    try:
        theme = random.choice(themes)
        print(f"[send_video_to_channel] Tema seleccionado para canal {channel_id}: {theme}")
        
        videos = await get_instagram_reels_by_hashtag(theme, count=10, force_refresh=True)
        if not videos:
            print(f"[send_video_to_channel] No se encontraron Reels para el tema: {theme} en canal {channel_id}")
            return
        
        available_videos = [video for video in videos if video['url'] not in recently_sent_videos]
        if not available_videos:
            recently_sent_videos.clear()
            available_videos = videos
        
        video_info = random.choice(available_videos)
        video_url = video_info['url']
        
        recently_sent_videos.append(video_url)
        if len(recently_sent_videos) > 10:
            recently_sent_videos.pop(0)
        
        embedez_url = transform_to_embedez_url(video_url)
        if not embedez_url:
            print(f"[send_video_to_channel] Error: No se pudo transformar el enlace: {video_url} para canal {channel_id}")
            return
        
        content_msg = f"📱 Reel automático de **{theme}**:\n{embedez_url}"
        
        channel = bot.get_channel(channel_id)
        if channel:
            permissions = channel.permissions_for(channel.guild.me)
            if permissions.send_messages:
                try:
                    await channel.send(content=content_msg)
                    print(f"[send_video_to_channel] Reel enviado a {channel.name} ({channel_id})")
                except Exception as e:
                    print(f"[send_video_to_channel] Error al enviar a {channel_id}: {e}")
            else:
                print(f"[send_video_to_channel] Sin permisos para enviar en {channel.name} ({channel_id})")
        else:
            print(f"[send_video_to_channel] No se encontró el canal con ID {channel_id}")
        
    except Exception as e:
        print(f"[send_video_to_channel] Error en la tarea automática para canal {channel_id}: {e}")
        traceback.print_exc()

# Función para crear una tarea de envío para un canal
def create_channel_task(channel_id, interval, unit):
    interval_seconds = get_interval_in_seconds(interval, unit)

    @tasks.loop(seconds=interval_seconds)
    async def channel_task():
        await send_video_to_channel(channel_id)

    channel_task.start()
    return channel_task

# Función para iniciar todas las tareas de los canales
def start_channel_tasks():
    global channel_tasks
    for channel in channels:
        channel_id = channel["channel_id"]
        interval = channel["interval"]
        unit = channel["unit"]
        if channel_id not in channel_tasks:
            task = create_channel_task(channel_id, interval, unit)
            channel_tasks[channel_id] = task
            print(f"[start_channel_tasks] Tarea iniciada para canal {channel_id} con intervalo {interval} {unit}")

# Función para detener todas las tareas de los canales
def stop_channel_tasks():
    global channel_tasks
    for channel_id, task in channel_tasks.items():
        if task.is_running():
            task.stop()
            print(f"[stop_channel_tasks] Tarea detenida para canal {channel_id}")
    channel_tasks.clear()

# Comando para agregar un canal a la lista
@bot.command(name='agregar_canal')
async def add_channel(ctx, channel_id: str, interval: int, unit: str):
    global channels
    now = time.time()
    if ctx.message.id in message_timestamps and now - message_timestamps[ctx.message.id] < 5:
        return
    message_timestamps[ctx.message.id] = now
    
    # Extraer el ID del canal, ya sea que se pase como mención (<#ID>) o como número
    try:
        if channel_id.startswith('<#') and channel_id.endswith('>'):
            channel_id = channel_id[2:-1]  # Quitamos "<#" y ">"
        channel_id = int(channel_id)
    except ValueError:
        await ctx.send("❌ Por favor, ingresa un ID de canal válido (puede ser un número o una mención de canal).")
        return
    
    channel = bot.get_channel(channel_id)
    if channel is None:
        await ctx.send(f"❌ No se encontró el canal con ID {channel_id}.")
        return
    
    # Validar intervalo y unidad
    unit = unit.lower()
    if unit not in ["minutes", "hours", "days"]:
        await ctx.send("❌ Unidad de tiempo no válida. Usa 'minutes', 'hours' o 'days'.")
        return
    
    if interval <= 0:
        await ctx.send("❌ El intervalo debe ser un número mayor que 0.")
        return
    
    if unit == "minutes" and interval < 1:
        await ctx.send("❌ Para 'minutes', el intervalo mínimo es 1 minuto.")
        return
    if unit == "hours" and interval < 1:
        await ctx.send("❌ Para 'hours', el intervalo mínimo es 1 hora.")
        return
    if unit == "days" and interval < 1:
        await ctx.send("❌ Para 'days', el intervalo mínimo es 1 día.")
        return

    # Verificar si el canal ya está en la lista
    for ch in channels:
        if ch["channel_id"] == channel_id:
            await ctx.send(f"⚠️ El canal <#{channel_id}> ya está en la lista.")
            return
    
    # Agregar el canal con su intervalo
    channels.append({"channel_id": channel_id, "interval": interval, "unit": unit})
    save_channels(channels)
    
    # Detener y reiniciar las tareas para incluir el nuevo canal
    stop_channel_tasks()
    start_channel_tasks()
    
    await ctx.send(f"✅ Canal <#{channel_id}> agregado a la lista de envío automático con intervalo de {interval} {unit}.")

# Comando slash para agregar un canal
@bot.tree.command(name="agregar_canal", description="Agrega un canal a la lista de envío automático de videos")
async def slash_add_channel(interaction: discord.Interaction, channel_id: int, interval: int, unit: str):
    global channels
    channel = bot.get_channel(channel_id)
    if channel is None:
        await interaction.response.send_message(f"❌ No se encontró el canal con ID {channel_id}.", ephemeral=True)
        return
    
    # Validar intervalo y unidad
    unit = unit.lower()
    if unit not in ["minutes", "hours", "days"]:
        await interaction.response.send_message("❌ Unidad de tiempo no válida. Usa 'minutes', 'hours' o 'days'.", ephemeral=True)
        return
    
    if interval <= 0:
        await interaction.response.send_message("❌ El intervalo debe ser un número mayor que 0.", ephemeral=True)
        return
    
    if unit == "minutes" and interval < 1:
        await interaction.response.send_message("❌ Para 'minutes', el intervalo mínimo es 1 minuto.", ephemeral=True)
        return
    if unit == "hours" and interval < 1:
        await interaction.response.send_message("❌ Para 'hours', el intervalo mínimo es 1 hora.", ephemeral=True)
        return
    if unit == "days" and interval < 1:
        await interaction.response.send_message("❌ Para 'days', el intervalo mínimo es 1 día.", ephemeral=True)
        return

    # Verificar si el canal ya está en la lista
    for ch in channels:
        if ch["channel_id"] == channel_id:
            await interaction.response.send_message(f"⚠️ El canal <#{channel_id}> ya está en la lista.", ephemeral=True)
            return
    
    # Agregar el canal con su intervalo
    channels.append({"channel_id": channel_id, "interval": interval, "unit": unit})
    save_channels(channels)
    
    # Detener y reiniciar las tareas para incluir el nuevo canal
    stop_channel_tasks()
    start_channel_tasks()
    
    await interaction.response.send_message(f"✅ Canal <#{channel_id}> agregado a la lista de envío automático con intervalo de {interval} {unit}.")

# Comando para eliminar un canal de la lista
@bot.command(name='eliminar_canal')
async def remove_channel(ctx, channel_id: int):
    global channels
    now = time.time()
    if ctx.message.id in message_timestamps and now - message_timestamps[ctx.message.id] < 5:
        return
    message_timestamps[ctx.message.id] = now
    
    # Buscar y eliminar el canal
    for ch in channels:
        if ch["channel_id"] == channel_id:
            channels.remove(ch)
            save_channels(channels)
            # Detener y reiniciar las tareas
            stop_channel_tasks()
            start_channel_tasks()
            await ctx.send(f"✅ Canal <#{channel_id}> eliminado de la lista de envío automático.")
            return
    
    await ctx.send(f"❌ El canal <#{channel_id}> no está en la lista.")

# Comando slash para eliminar un canal
@bot.tree.command(name="eliminar_canal", description="Elimina un canal de la lista de envío automático de videos")
async def slash_remove_channel(interaction: discord.Interaction, channel_id: int):
    global channels
    for ch in channels:
        if ch["channel_id"] == channel_id:
            channels.remove(ch)
            save_channels(channels)
            # Detener y reiniciar las tareas
            stop_channel_tasks()
            start_channel_tasks()
            await interaction.response.send_message(f"✅ Canal <#{channel_id}> eliminado de la lista de envío automático.")
            return
    
    await interaction.response.send_message(f"❌ El canal <#{channel_id}> no está en la lista.", ephemeral=True)

# Comando para ver la lista de canales
@bot.command(name='ver_canales')
async def view_channels(ctx):
    global channels
    now = time.time()
    if ctx.message.id in message_timestamps and now - message_timestamps[ctx.message.id] < 5:
        return
    message_timestamps[ctx.message.id] = now
    
    if not channels:
        await ctx.send("📋 No hay canales asignados para envío automático.")
    else:
        channel_info = []
        for ch in channels:
            channel_info.append(f"<#{ch['channel_id']}> (cada {ch['interval']} {ch['unit']})")
        channel_list = ', '.join(channel_info)
        await ctx.send(f"📋 Canales para envío automático: {channel_list}")

# Comando slash para ver la lista de canales
@bot.tree.command(name="ver_canales", description="Muestra la lista de canales para envío automático de videos")
async def slash_view_channels(interaction: discord.Interaction):
    global channels
    if not channels:
        await interaction.response.send_message("📋 No hay canales asignados para envío automático.", ephemeral=True)
    else:
        channel_info = []
        for ch in channels:
            channel_info.append(f"<#{ch['channel_id']}> (cada {ch['interval']} {ch['unit']})")
        channel_list = ', '.join(channel_info)
        await interaction.response.send_message(f"📋 Canales para envío automático: {channel_list}")

# Comando para limpiar el caché
@bot.command(name='limpiar_cache')
async def clear_cache(ctx):
    global theme_video_registry
    now = time.time()
    if ctx.message.id in message_timestamps and now - message_timestamps[ctx.message.id] < 5:
        return
    message_timestamps[ctx.message.id] = now
    
    try:
        theme_video_registry = {}
        if os.path.exists(THEME_VIDEO_REGISTRY):
            os.remove(THEME_VIDEO_REGISTRY)
        await ctx.send("✅ Caché de videos limpiado correctamente.")
        print("[clear_cache] Caché limpiado por el usuario.")
    except Exception as e:
        await ctx.send(f"❌ Error al limpiar el caché: {str(e)}")
        print(f"[clear_cache] Error al limpiar el caché: {e}")

# Comando slash para limpiar el caché
@bot.tree.command(name="limpiar_cache", description="Limpia el caché de videos almacenados")
async def slash_clear_cache(interaction: discord.Interaction):
    global theme_video_registry
    await interaction.response.defer(ephemeral=False)
    try:
        theme_video_registry = {}
        if os.path.exists(THEME_VIDEO_REGISTRY):
            os.remove(THEME_VIDEO_REGISTRY)
        await interaction.followup.send("✅ Caché de videos limpiado correctamente.")
        print("[slash_clear_cache] Caché limpiado por el usuario.")
    except Exception as e:
        await interaction.followup.send(f"❌ Error al limpiar el caché: {str(e)}")
        print(f"[slash_clear_cache] Error al limpiar el caché: {e}")

# Comando para configurar el intervalo de envío automático (ahora obsoleto, pero lo dejamos por compatibilidad)
@bot.command(name='configurar_intervalo')
async def configure_interval(ctx, interval: int, unit: str):
    global config
    now = time.time()
    if ctx.message.id in message_timestamps and now - message_timestamps[ctx.message.id] < 5:
        return
    message_timestamps[ctx.message.id] = now
    
    await ctx.send("⚠️ Este comando está obsoleto. Ahora puedes configurar intervalos individuales al agregar un canal con `_agregar_canal` o `/agregar_canal`.")

# Comando slash para configurar el intervalo (obsoleto)
@bot.tree.command(name="configurar_intervalo", description="Configura el intervalo de envío automático de videos")
async def slash_configure_interval(interaction: discord.Interaction, interval: int, unit: str):
    await interaction.response.send_message("⚠️ Este comando está obsoleto. Ahora puedes configurar intervalos individuales al agregar un canal con `/agregar_canal`.", ephemeral=True)

# Comando para asignar temas (hashtags)
@bot.command(name='asignar_tema')
async def assign_theme(ctx, *args):
    global themes
    now = time.time()
    if ctx.message.id in message_timestamps and now - message_timestamps[ctx.message.id] < 5:
        return
    message_timestamps[ctx.message.id] = now
    new_themes = list(set(filter(None, args)))
    if not new_themes:
        await ctx.send("Por favor, proporciona al menos un tema válido.")
        return
    already_added = [theme for theme in new_themes if theme in themes]
    new_to_add = [theme for theme in new_themes if theme not in themes]
    if already_added and not new_to_add:
        await ctx.send(f"Los siguientes temas ya están agregados: {', '.join(already_added)}.\nTemas actuales: {', '.join(themes)}")
    elif new_to_add and not already_added:
        themes.extend(new_to_add)
        save_themes()
        await ctx.send(f"Nuevos temas agregados: {', '.join(new_to_add)}.\nTemas actuales: {', '.join(themes)}")
    elif new_to_add and already_added:
        themes.extend(new_to_add)
        save_themes()
        await ctx.send(
            f"Los siguientes temas ya estaban agregados: {', '.join(already_added)}.\n"
            f"Nuevos temas agregados: {', '.join(new_to_add)}.\n"
            f"Temas actuales: {', '.join(themes)}"
        )

# Comando para eliminar un tema (hashtag)
@bot.command(name='eliminar_tema')
async def remove_theme(ctx, theme: str):
    global themes
    now = time.time()
    if ctx.message.id in message_timestamps and now - message_timestamps[ctx.message.id] < 5:
        return
    message_timestamps[ctx.message.id] = now
    if theme in themes:
        themes.remove(theme)
        save_themes()
        await ctx.send(f'Tema eliminado: {theme}')
    else:
        await ctx.send(f'El tema "{theme}" no se encuentra en la lista.')

# Comando para ver todos los temas asignados
@bot.command(name='ver_temas')
async def view_themes(ctx):
    now = time.time()
    if ctx.message.id in message_timestamps and now - message_timestamps[ctx.message.id] < 5:
        return
    message_timestamps[ctx.message.id] = now
    if themes:
        await ctx.send(f'Temas asignados: {", ".join(themes)}')
    else:
        await ctx.send("No hay temas asignados actualmente.")

# --- COMANDOS DE APLICACIÓN (SLASH COMMANDS) ---
@bot.tree.command(name="asignar_tema", description="Asigna uno o más temas/hashtags para buscar Instagram Reels")
async def slash_assign_theme(interaction: discord.Interaction, temas: str):
    global themes
    args = temas.split()
    new_themes = list(set(filter(None, args)))
    if not new_themes:
        await interaction.response.send_message("Por favor, proporciona al menos un tema válido.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=False)
    already_added = [theme for theme in new_themes if theme in themes]
    new_to_add = [theme for theme in new_themes if theme not in themes]
    if already_added and not new_to_add:
        await interaction.followup.send(f"Los siguientes temas ya están agregados: {', '.join(already_added)}.\nTemas actuales: {', '.join(themes)}")
    elif new_to_add and not already_added:
        themes.extend(new_to_add)
        save_themes()
        await interaction.followup.send(f"Nuevos temas agregados: {', '.join(new_to_add)}.\nTemas actuales: {', '.join(themes)}")
    elif new_to_add and already_added:
        themes.extend(new_to_add)
        save_themes()
        await interaction.followup.send(
            f"Los siguientes temas ya estaban agregados: {', '.join(already_added)}.\n"
            f"Nuevos temas agregados: {', '.join(new_to_add)}.\n"
            f"Temas actuales: {', '.join(themes)}"
        )

@bot.tree.command(name="eliminar_tema", description="Elimina un tema/hashtag de la lista")
async def slash_remove_theme(interaction: discord.Interaction, tema: str):
    global themes
    if tema in themes:
        themes.remove(tema)
        save_themes()
        await interaction.response.send_message(f'✅ Tema eliminado: {tema}')
    else:
        await interaction.response.send_message(f'❌ El tema "{tema}" no se encuentra en la lista.')

@bot.tree.command(name="ver_temas", description="Muestra todos los temas/hashtags actualmente asignados")
async def slash_view_themes(interaction: discord.Interaction):
    global themes
    if themes:
        await interaction.response.send_message(f'📋 Temas asignados: {", ".join(themes)}')
    else:
        await interaction.response.send_message("📋 No hay temas asignados actualmente.")

@bot.tree.command(name="ayuda", description="Muestra la lista de comandos disponibles")
async def slash_help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📱 Ayuda del Bot Brainrot",
        description="Aquí encontrarás todos los comandos disponibles para interactuar con el bot.",
        color=0xFF0050
    )
    embed.set_thumbnail(url="https://i.imgur.com/OGwYwj9.png")
    embed.add_field(
        name="🏷️ Gestión de Temas",
        value=(
            "**`/asignar_tema`** o **`_asignar_tema`**\n"
            "➡️ Asigna uno o más temas (hashtags) para buscar Reels.\n"
            "➡️ Ejemplo: `/asignar_tema temas:#meme #funny` o `_asignar_tema #meme #funny`\n\n"
            "**`/eliminar_tema`** o **`_eliminar_tema`**\n"
            "➡️ Elimina un tema de la lista.\n"
            "➡️ Ejemplo: `/eliminar_tema tema:#meme` o `_eliminar_tema #meme`\n\n"
            "**`/ver_temas`** o **`_ver_temas`**\n"
            "➡️ Muestra los temas actualmente asignados."
        ),
        inline=False
    )
    embed.add_field(
        name="🎬 Instagram Reels",
        value=(
            "**`/enviar_video`** o **`_enviar_video`**\n"
            "➡️ Envía un Instagram Reel aleatorio basado en los temas asignados.\n\n"
            "**`/video_directo`** o **`_video_directo`**\n"
            "➡️ Envía un Reel específico dado su URL de Instagram.\n"
            "➡️ Ejemplo: `/video_directo url:https://www.instagram.com/reel/ABC123/`"
        ),
        inline=False
    )
    embed.add_field(
        name="📺 Gestión de Canales",
        value=(
            "**`/agregar_canal`** o **`_agregar_canal`**\n"
            "➡️ Agrega un canal a la lista de envío automático.\n"
            "➡️ Ejemplo: `/agregar_canal channel_id:123456789 interval:5 unit:minutes`\n\n"
            "**`/eliminar_canal`** o **`_eliminar_canal`**\n"
            "➡️ Elimina un canal de la lista de envío automático.\n"
            "➡️ Ejemplo: `/eliminar_canal channel_id:123456789` o `_eliminar_canal 123456789`\n\n"
            "**`/ver_canales`** o **`_ver_canales`**\n"
            "➡️ Muestra la lista de canales para envío automático."
        ),
        inline=False
    )
    embed.add_field(
        name="🧹 Limpiar Caché",
        value=(
            "**`/limpiar_cache`** o **`_limpiar_cache`**\n"
            "➡️ Limpia el caché de videos almacenados."
        ),
        inline=False
    )
    embed.add_field(
        name="❓ Ayuda",
        value=(
            "**`/ayuda`** o **`_ayuda`**\n"
            "➡️ Muestra este mensaje de ayuda."
        ),
        inline=False
    )
    embed.add_field(
        name="📝 Notas",
        value=(
            "• Usa comandos con `/` o con prefijo `_`.\n"
            "• Los temas y canales se guardan automáticamente.\n"
            "• Los Reels se envían según los intervalos configurados por canal."
        ),
        inline=False
    )
    embed.set_footer(text=f"Bot Instagram Reels • Solicitado por {interaction.user.name}", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
    embed.timestamp = discord.utils.utcnow()
    await interaction.response.send_message(embed=embed)

# Comando con prefijo para enviar un video
@bot.command(name='enviar_video')
async def prefix_send_video(ctx):
    global themes, instagram_connected, recently_sent_videos
    now = time.time()
    if ctx.message.id in message_timestamps and now - message_timestamps[ctx.message.id] < 5:
        return
    message_timestamps[ctx.message.id] = now
    
    if not themes:
        await ctx.send("No hay temas asignados. Usa `_asignar_tema` para añadir algunos.")
        return
    
    if not instagram_connected:
        await ctx.send("⌛ Conexión con Instagram en proceso. Espera unos segundos.")
        return
    
    loading_msg = await ctx.send("🔍 Buscando un Reel aleatorio...")
    try:
        theme = random.choice(themes)
        print(f"[_enviar_video] Tema seleccionado: {theme}")
        
        await loading_msg.edit(content=f"🔍 Buscando Reels para **{theme}**...")
        force_refresh = random.random() < 0.2
        videos = await get_instagram_reels_by_hashtag(theme, count=10, force_refresh=force_refresh)
        
        if not videos:
            await ctx.send(f"⚠️ No se encontraron Reels para el tema: **{theme}**. Intenta con otro tema o usa `_limpiar_cache`.")
            await loading_msg.delete()
            return
        
        available_videos = [video for video in videos if video['url'] not in recently_sent_videos]
        if not available_videos:
            recently_sent_videos.clear()
            available_videos = videos
        
        video_info = random.choice(available_videos)
        video_url = video_info['url']
        
        recently_sent_videos.append(video_url)
        if len(recently_sent_videos) > 10:
            recently_sent_videos.pop(0)
        
        embedez_url = transform_to_embedez_url(video_url)
        if not embedez_url:
            await ctx.send(f"❌ Error: No se pudo transformar el enlace del Reel: {video_url}")
            await loading_msg.delete()
            return
        
        content_msg = f"📱 Aquí tienes un Instagram Reel de **{theme}**:\n{embedez_url}"
        await ctx.send(content=content_msg)
        await loading_msg.delete()
            
    except Exception as e:
        error_msg = str(e)
        await ctx.send(f"❌ Error al obtener el Reel: {error_msg}")
        print(f"[_enviar_video] Error: {error_msg}")
        traceback.print_exc()

# Comando slash para enviar un video
@bot.tree.command(name="enviar_video", description="Envía un Instagram Reel aleatorio basado en los temas asignados")
async def slash_send_video(interaction: discord.Interaction):
    global themes, instagram_connected, recently_sent_videos
    
    if not themes:
        await interaction.response.send_message("No hay temas asignados. Usa `/asignar_tema`.", ephemeral=True)
        return
    
    if not instagram_connected:
        await interaction.response.send_message("⌛ Conexión con Instagram en proceso. Espera unos segundos.", ephemeral=True)
        return
    
    await interaction.response.defer(thinking=True)
    
    try:
        theme = random.choice(themes)
        print(f"[/enviar_video] Tema seleccionado: {theme}")
        
        searching_msg = await interaction.followup.send(f"🔍 Buscando Reels de **{theme}**...")
        force_refresh = random.random() < 0.2
        videos = await get_instagram_reels_by_hashtag(theme, count=10, force_refresh=force_refresh)
        
        if not videos:
            await interaction.followup.send(f"⚠️ No se encontraron Reels para el tema: **{theme}**. Usa `/limpiar_cache` si persiste.")
            await searching_msg.delete()
            return
        
        available_videos = [video for video in videos if video['url'] not in recently_sent_videos]
        if not available_videos:
            recently_sent_videos.clear()
            available_videos = videos
        
        video_info = random.choice(available_videos)
        video_url = video_info['url']
        
        recently_sent_videos.append(video_url)
        if len(recently_sent_videos) > 10:
            recently_sent_videos.pop(0)
        
        embedez_url = transform_to_embedez_url(video_url)
        if not embedez_url:
            await interaction.followup.send(f"❌ Error: No se pudo transformar el enlace: {video_url}")
            await searching_msg.delete()
            return
        
        content_msg = f"📱 Aquí tienes un Instagram Reel de **{theme}**:\n{embedez_url}"
        await interaction.followup.send(content=content_msg)
        await searching_msg.delete()
            
    except Exception as e:
        error_msg = str(e)
        await interaction.followup.send(f"❌ Error al obtener el Reel: {error_msg}")
        print(f"[/enviar_video] Error: {error_msg}")
        traceback.print_exc()

# Comando para enviar un Reel específico
@bot.tree.command(name="video_directo", description="Envía un Reel específico dado su URL de Instagram")
async def video_directo(interaction: discord.Interaction, url: str):
    if 'instagram.com' not in url:
        await interaction.response.send_message("❌ Proporciona una URL válida de Instagram Reels.", ephemeral=True)
        return
        
    await interaction.response.defer(thinking=True)
    
    try:
        searching_msg = await interaction.followup.send("⬇️ Verificando enlace...")
        is_valid = await is_valid_instagram_url(url)
        if not is_valid:
            await interaction.followup.send("❌ El enlace no es válido o el Reel no está disponible.")
            await searching_msg.delete()
            return
            
        embedez_url = transform_to_embedez_url(url)
        if not embedez_url:
            await interaction.followup.send(f"❌ Error: No se pudo transformar el enlace: {url}")
            await searching_msg.delete()
            return
        
        await interaction.followup.send(f"📱 Aquí tienes tu Reel de Instagram:\n{embedez_url}")
        await searching_msg.delete()
            
    except Exception as e:
        error_msg = str(e)
        await interaction.followup.send(f"❌ Error al procesar el Reel: {error_msg}")
        print(f"[video_directo] Error: {error_msg}")

# Comando con prefijo para enviar un Reel específico
@bot.command(name='video_directo')
async def prefix_video_directo(ctx, url: str):
    now = time.time()
    if ctx.message.id in message_timestamps and now - message_timestamps[ctx.message.id] < 5:
        return
    message_timestamps[ctx.message.id] = now
    
    if 'instagram.com' not in url:
        await ctx.send("❌ Proporciona una URL válida de Instagram Reels.")
        return
        
    loading_msg = await ctx.send("⬇️ Verificando enlace...")
    
    try:
        is_valid = await is_valid_instagram_url(url)
        if not is_valid:
            await ctx.send("❌ El enlace no es válido o el Reel no está disponible.")
            await loading_msg.delete()
            return
                
        embedez_url = transform_to_embedez_url(url)
        if not embedez_url:
            await ctx.send(f"❌ Error: No se pudo transformar el enlace: {url}")
            await loading_msg.delete()
            return
        
        await ctx.send(f"📱 Aquí tienes tu Reel de Instagram:\n{embedez_url}")
        await loading_msg.delete()
            
    except Exception as e:
        error_msg = str(e)
        await ctx.send(f"❌ Error: {error_msg}")
        print(f"[_video_directo] Error: {error_msg}")

# Tarea para limpiar mensajes temporales
@tasks.loop(minutes=5)
async def clean_timestamps():
    now = time.time()
    for msg_id in list(message_timestamps.keys()):
        if now - message_timestamps[msg_id] > 600:
            del message_timestamps[msg_id]

# Tarea para limpiar la lista de videos recientes
@tasks.loop(hours=1)
async def clean_recent_videos():
    global recently_sent_videos
    recently_sent_videos.clear()
    print("[clean_recent_videos] Lista de videos recientes limpiada.")

# Iniciar el bot
if __name__ == "__main__":
    try:
        print("Iniciando bot de Discord...")
        bot.run(BOT_TOKEN)
    except Exception as e:
        print(f"Error fatal al iniciar el bot: {e}")
        traceback.print_exc()