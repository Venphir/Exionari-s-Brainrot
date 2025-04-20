import discord
from discord.ext import commands, tasks
from TikTokApi import TikTokApi
import random
import os
from dotenv import load_dotenv
import json
import asyncio
import time
import tempfile
import yt_dlp  # Nueva biblioteca para descargar videos
import subprocess  # Para llamar a ffmpeg para compresión
import math  # Para cálculos de calidad de compresión
import requests as http_requests  # Renombrar para evitar conflictos

import pickle

# Cargar variables de entorno desde el archivo .env
dotenv_path = ".env"
if not os.path.exists(dotenv_path):
    raise FileNotFoundError(f"No se encontró el archivo .env en la ruta: {dotenv_path}")

load_dotenv(dotenv_path=dotenv_path)

# Directorio para almacenamiento de caché de videos
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "video_cache")
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

# Registro de videos por tema - ayuda a rastrear qué videos están asociados con cada tema
THEME_VIDEO_REGISTRY = os.path.join(CACHE_DIR, "theme_videos.pkl")

# Cargar registro de temas-videos o crear uno nuevo
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
bot = commands.Bot(command_prefix='_', intents=intents, help_command=None)  # Desactivar comando de ayuda predeterminado

# Configuración de la API de TikTok
# Como estamos usando el método embedez, realmente no necesitamos la API de TikTok
# Por lo que podemos dejarla como None y modificar el código para que no dependa de ella
api = None
try:
    # Solo inicializar la API si se requiere funcionalidad adicional
    if os.getenv("USE_TIKTOK_API", "false").lower() == "true":
        print("Inicializando TikTokApi (esto puede tardar)...")
        api = TikTokApi()
        loop = asyncio.get_event_loop()
        loop.run_until_complete(api.create_sessions())
        print("TikTokApi inicializada correctamente.")
    else:
        print("Modo embedez: TikTokApi no será inicializada")
except Exception as e:
    print(f"Error al inicializar TikTokApi: {e}")
    print("El bot continuará usando el modo embedez sin la API de TikTok")
    api = None

# Ruta del archivo para almacenar los temas
themes_file = "themes.json"

# Configuración del canal desde el archivo .env
# Intentar obtener el ID con manejo mejorado de errores
try:
    channel_id_str = os.getenv("DISCORD_CHANNEL_ID")
    if not channel_id_str:
        print("⚠️ ADVERTENCIA: ID del canal no encontrado en .env")
        print("Los comandos automáticos no funcionarán hasta que configures DISCORD_CHANNEL_ID")
        channel_id = None
    else:
        channel_id = int(channel_id_str)
        print(f"Canal configurado: {channel_id}")
except ValueError:
    print(f"⚠️ ERROR: El ID del canal '{channel_id_str}' no es un número válido")
    print("Por favor corrige el valor en el archivo .env")
    channel_id = None

# Una estrategia más simple para evitar comandos duplicados
message_timestamps = {}
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
# Función para guardar los temas en el archivo de manera no bloqueante
def save_themes():
    # Crea una copia local de themes para evitar problemas de concurrencia
    themes_copy = themes.copy()
    with open(themes_file, "w", encoding="utf-8") as f:
        json.dump(themes_copy, f, ensure_ascii=False, indent=4)
    print("Temas guardados correctamente.")
# Lista para almacenar los temas asignados
themes = []
# Cargar los temas al iniciar el bot
load_themes()
# Comando para asignar temas (hashtags)
@bot.command(name='asignar_tema')
async def assign_theme(ctx, *args):
    global themes
    # Evitar procesamiento duplicado
    now = time.time()
    if ctx.message.id in message_timestamps and now - message_timestamps[ctx.message.id] < 5:
        return
    message_timestamps[ctx.message.id] = now
    new_themes = list(set(filter(None, args)))  # Filtrar temas vacíos
    if not new_themes:
        await ctx.send("Por favor, proporciona al menos un tema válido. Los temas vacíos no son permitidos.")
        return
    already_added = [theme for theme in new_themes if theme in themes]
    new_to_add = [theme for theme in new_themes if theme not in themes]
    # Solo un mensaje de respuesta, según el caso
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
    # Evitar procesamiento duplicado
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
    # Evitar procesamiento duplicado
    now = time.time()
    if ctx.message.id in message_timestamps and now - message_timestamps[ctx.message.id] < 5:
        return
    message_timestamps[ctx.message.id] = now
    if themes:
        await ctx.send(f'Temas asignados: {", ".join(themes)}')
    else:
        await ctx.send("No hay temas asignados actualmente.")
    
# --- COMANDOS DE APLICACIÓN (SLASH COMMANDS) ---
@bot.tree.command(name="asignar_tema", description="Asigna uno o más temas/hashtags para buscar videos de TikTok")
async def slash_assign_theme(interaction: discord.Interaction, temas: str):
    global themes
    # Dividir los temas ingresados (separados por espacios)
    args = temas.split()
    new_themes = list(set(filter(None, args)))  # Filtrar temas vacíos
    if not new_themes:
        await interaction.response.send_message("Por favor, proporciona al menos un tema válido. Los temas vacíos no son permitidos.", ephemeral=True)
        return
    # Responder inmediatamente
    await interaction.response.defer(ephemeral=False)
    already_added = [theme for theme in new_themes if theme in themes]
    new_to_add = [theme for theme in new_themes if theme not in themes]
    # Solo un mensaje de respuesta, según el caso
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
    # Crear un embed con colores y formato profesional
    embed = discord.Embed(
        title="📱 Ayuda del Bot Brainrot",
        description="Aquí encontrarás todos los comandos disponibles para interactuar con el bot.",
        color=0xFF0050  # Rosa TikTok
    )
    # Agregar thumbnail (icono pequeño en la esquina)
    embed.set_thumbnail(url="https://i.imgur.com/OGwYwj9.png")  # Logo de TikTok
    
    # Comandos para gestión de temas
    embed.add_field(
        name="🏷️ Gestión de Temas",
        value=(
            "**`/asignar_tema`** o **`_asignar_tema`**\n"
            "➡️ Asigna uno o más temas (hashtags) para buscar videos.\n"
            "➡️ Ejemplo: `/asignar_tema temas:#meme #funny` o `_asignar_tema #meme #funny`\n\n"
            "**`/eliminar_tema`** o **`_eliminar_tema`**\n"
            "➡️ Elimina un tema de la lista.\n"
            "➡️ Ejemplo: `/eliminar_tema tema:#meme` o `_eliminar_tema #meme`\n\n"
            "**`/ver_temas`** o **`_ver_temas`**\n"
            "➡️ Muestra los temas actualmente asignados."
        ),
        inline=False
    )
    
    # Comandos para videos
    embed.add_field(
        name="🎬 Videos de TikTok",
        value=(
            "**`/enviar_video`** o **`_enviar_video`**\n"
            "➡️ Envía un video aleatorio de TikTok basado en los temas asignados.\n"
            "➡️ El comando slash aparece en el menú al escribir `/`"
        ),
        inline=False
    )
            
    # Comandos de ayuda
    embed.add_field(
        name="❓ Ayuda",
        value=(
            "**`/ayuda`** o **`_ayuda`**\n"
            "➡️ Muestra este mensaje de ayuda."
        ),
        inline=False
    )
    
    # Nota adicional
    embed.add_field(
        name="📝 Notas",
        value=(
            "• Puedes usar comandos con barra diagonal (`/`) o con prefijo (`_`).\n"
            "• Los temas asignados se guardan automáticamente.\n"
            "• Para que el bot funcione correctamente, debe tener permisos para enviar mensajes y archivos."
        ),
        inline=False
    )
    
    # Pie de página
    embed.set_footer(text=f"Bot TikTok • Solicitado por {interaction.user.name}", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
    # Agregar timestamp
    embed.timestamp = discord.utils.utcnow()
    await interaction.response.send_message(embed=embed)
# --- COMANDOS CON PREFIJO ---
# Comando con prefijo para enviar un video (complemento al comando slash existente)
@bot.command(name='enviar_video')
async def prefix_send_video(ctx):
    global themes
    # Evitar procesamiento duplicado
    now = time.time()
    if ctx.message.id in message_timestamps and now - message_timestamps[ctx.message.id] < 5:
        return
    message_timestamps[ctx.message.id] = now
    
    if not themes:
        await ctx.send("No hay temas asignados. Usa `_asignar_tema` para añadir algunos.")
        return
    if not api:
        await ctx.send("Error: TikTokApi no está configurada correctamente.")
        return

    # Informar al usuario
    loading_msg = await ctx.send("🔍 Buscando un video aleatorio... Por favor espera.")
    try:
        # Seleccionar un tema aleatorio
        theme = random.choice(themes)
        print(f"[_enviar_video] Tema seleccionado: {theme}")
        # USAR EL NUEVO MÉTODO DE BÚSQUEDA
        videos = await get_tiktok_videos_by_hashtag(theme, count=5)
        if not videos:
            await ctx.send(f"⚠️ No se encontraron videos para el tema: **{theme}**")
            return
        # Seleccionar un video aleatorio 
        video_info = random.choice(videos)
        video_url = video_info['url']
        print(f"[_enviar_video] Video seleccionado: {video_url}")
        # Actualizar el mensaje
        await loading_msg.edit(content=f"⬇️ Preparando video de **{theme}**... Por favor espera.")
        # Usar la función modificada que ahora devuelve (file_path, embedez_url)
        video_file, embedez_url = await download_tiktok_video(video_url)
        
        # Si tenemos una URL de embedez, la usamos (caso normal)
        if embedez_url:
            content_msg = f"🎬 Aquí tienes un video de **{theme}**: {embedez_url}"
            await ctx.send(content=content_msg)
            
            # Eliminar el mensaje de carga
            try:
                await loading_msg.delete()
            except:
                pass
        
        # Si tenemos un archivo local (caso de fallback), lo enviamos
        elif video_file:
            content_msg = f"⚠️ No se pudo obtener el video de TikTok. Aquí tienes un video de respaldo para **{theme}**."
            await ctx.send(
                content=content_msg,
                file=discord.File(video_file)
            )
            
            # Eliminar el mensaje de carga
            try:
                await loading_msg.delete()
            except:
                pass
        
        # Si no tenemos ni url ni archivo (error total)
        else:
            await ctx.send(f"⚠️ No se pudo procesar el video. Aquí está el enlace original: {video_url}")
            
    except Exception as e:
        error_msg = str(e)
        await ctx.send(f"❌ Error al obtener el video: {error_msg}")
        print(f"Error en _enviar_video: {error_msg}")
        
# Actualizar el comando de ayuda con prefijo para mostrar ambas opciones
@bot.command(name='ayuda')
async def prefix_help_command(ctx):
    # Evitar procesamiento duplicado
    now = time.time()
    if ctx.message.id in message_timestamps and now - message_timestamps[ctx.message.id] < 5:
        return
    message_timestamps[ctx.message.id] = now
    # Crear un embed con colores y formato profesional
    embed = discord.Embed(
        title="📱 Ayuda del Bot Brainrot",
        description="Aquí encontrarás todos los comandos disponibles para interactuar con el bot.",
        color=0xFF0050  # Rosa TikTok
    )
    # Agregar thumbnail (icono pequeño en la esquina)
    embed.set_thumbnail(url="https://i.imgur.com/OGwYwj9.png")  # Logo de TikTok
    # Comandos para gestión de temas
    embed.add_field(
        name="🏷️ Gestión de Temas",
        value=(
            "**`/asignar_tema`** o **`_asignar_tema`**\n"
            "➡️ Asigna uno o más temas (hashtags) para buscar videos.\n"
            "➡️ Ejemplo: `/asignar_tema temas:#meme #funny` o `_asignar_tema #meme #funny`\n\n"
            "**`/eliminar_tema`** o **`_eliminar_tema`**\n"
            "➡️ Elimina un tema de la lista.\n"
            "➡️ Ejemplo: `/eliminar_tema tema:#meme` o `_eliminar_tema #meme`\n\n"
            "**`/ver_temas`** o **`_ver_temas`**\n"
            "➡️ Muestra los temas actualmente asignados."
        ),
        inline=False
    )
    
    # Comandos para videos
    embed.add_field(
        name="🎬 Videos de TikTok",
        value=(
            "**`/enviar_video`** o **`_enviar_video`**\n"
            "➡️ Envía un video aleatorio de TikTok basado en los temas asignados.\n"
            "➡️ El comando slash aparece en el menú al escribir `/`"
        ),
        inline=False
    )
            
    # Comandos de ayuda
    embed.add_field(
        name="❓ Ayuda",
        value=(
            "**`/ayuda`** o **`_ayuda`**\n"
            "➡️ Muestra este mensaje de ayuda."
        ),
        inline=False
    )
    
    # Nota adicional
    embed.add_field(
        name="📝 Notas",
        value=(
            "• Puedes usar comandos con barra diagonal (`/`) o con prefijo (`_`).\n"
            "• Los temas asignados se guardan automáticamente.\n"
            "• Para que el bot funcione correctamente, debe tener permisos para enviar mensajes y archivos."
        ),
        inline=False
    )
    
    # Pie de página
    embed.set_footer(text=f"Bot TikTok • Solicitado por {ctx.author.name}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
    # Agregar timestamp
    embed.timestamp = discord.utils.utcnow()
    await ctx.send(embed=embed)
# Limpieza periódica de timestamps antiguos
@tasks.loop(minutes=5)
async def clean_timestamps():
    now = time.time()
    # Eliminar entradas más viejas que 10 minutos
    for msg_id in list(message_timestamps.keys()):
        if now - message_timestamps[msg_id] > 600:  # 10 minutos
            del message_timestamps[msg_id]
# Lista actualizada de videos populares de TikTok que funcionan
FALLBACK_VIDEOS = [
    "https://www.tiktok.com/@domelipa/video/7336743194239773952",
    "https://www.tiktok.com/@charlidamelio/video/7335402374815719683",
    "https://www.tiktok.com/@khaby.lame/video/7334269282228271361",
    "https://www.tiktok.com/@addisonre/video/7336351380963021059",
    "https://www.tiktok.com/@bellapoarch/video/7334979323358730497",
    "https://www.tiktok.com/@zachking/video/7333128106586872070",
    "https://www.tiktok.com/@dixiedamelio/video/7336712928953299246",
    "https://www.tiktok.com/@willsmith/video/7331875805350704390",
    "https://www.tiktok.com/@therock/video/7336824451247317254",
    "https://www.tiktok.com/@jasonstatham/video/7336021733002168583"
]
# Función mejorada para buscar videos por hashtag con múltiples fuentes alternativas
async def get_tiktok_videos_by_hashtag(hashtag, count=5, use_cache=True):
    """Obtiene videos de TikTok relacionados con el hashtag usando múltiples métodos."""
    global theme_video_registry
    
    print(f"Buscando videos para hashtag: {hashtag}")
    hashtag_clean = hashtag.lstrip('#').lower()
    videos_info = []
    
    # NUEVO: Verificar primero el sistema de caché
    if use_cache and hashtag_clean in theme_video_registry:  # Corregido: && por and
        cached_videos = theme_video_registry.get(hashtag_clean, []) # Usar .get para evitar KeyError
        if cached_videos:
            print(f"Usando videos en caché para {hashtag_clean}, {len(cached_videos)} disponibles")
            # Barajar para no mostrar siempre los mismos
            random.shuffle(cached_videos)
            return cached_videos[:count]
    
    # MÉTODO 1: Búsqueda directa por tema en sitios alternativos
    try:
        # Conjunto de URLs alternativas para búsqueda (más probabilidades de éxito)
        urls_to_try = [
            f"https://tiktokder.com/api/short/search?keyword={hashtag_clean}&count=10",
            f"https://www.tiktok.com/api/search/general/full/?keyword={hashtag_clean}&is_filter_word=0&from_page=search",
            f"https://www.tikwm.com/api/feed/search?keywords={hashtag_clean}"
        ]
        # Headers que simulan navegador real
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'en-US,en;q=0.9,es;q=0.8',
            'Referer': 'https://www.google.com/',
            'Origin': 'https://www.google.com',
            'Sec-Fetch-Site': 'cross-site',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Dest': 'empty',
        }
        
        # Intentar cada URL hasta obtener resultados
        for api_url in urls_to_try:
            try:
                # Añadir manejo específico para errores de conexión/DNS
                response = http_requests.get(api_url, headers=headers, timeout=15) # Utilizar http_requests en lugar de requests
                response.raise_for_status() # Verificar errores HTTP
                
                # Procesar la respuesta JSON
                data = response.json()  # Asignar respuesta a la variable data
                
                # Extraer videos según la estructura de cada API
                if "data" in data:
                    # Formato API de TikTok
                    if isinstance(data["data"], list):
                        for item in data["data"][:count*2]:
                            if item.get('type') == 'video' and 'item' in item:
                                item_data = item['item']
                                if 'id' in item_data and 'author' in item_data:
                                    username = item_data['author'].get('uniqueId') or item_data['author'].get('nickname', 'tiktok_user')
                                    video_url = f"https://www.tiktok.com/@{username}/video/{item_data['id']}"
                                    videos_info.append({
                                        'id': item_data['id'],
                                        'url': video_url,
                                        'title': item_data.get('desc', f'Video de {username}'),
                                        'uploader': username
                                    })
                elif "videos" in data:
                    # Formato API de TikTokder
                    for video in data["videos"][:count*2]:
                        if 'video_id' in video:
                            video_url = f"https://www.tiktok.com/@{video.get('author', 'user')}/video/{video['video_id']}"
                            videos_info.append({
                                'id': video['video_id'],
                                'url': video_url,
                                'title': video.get('title', 'Video de TikTok'),
                                'uploader': video.get('author', 'TikTok user')
                            })
                elif "items" in data:
                    # Formato tikwm API
                    for video in data["items"][:count*2]:
                        if 'id' in video and 'author' in video:
                            video_url = video.get('share_url') or f"https://www.tiktok.com/@{video['author']['unique_id']}/video/{video['id']}"
                            videos_info.append({
                                'id': video['id'],
                                'url': video_url,
                                'title': video.get('title', 'Video de TikTok'),
                                'uploader': video['author'].get('unique_id', 'TikTok user')
                            })
                # Si encontramos suficientes videos, salimos
                if len(videos_info) >= count:
                    break
            except http_requests.exceptions.RequestException as e: # Capturar errores de requests
                print(f"Error de red/HTTP con API {api_url}: {e}")
                continue # Intentar la siguiente URL
            except json.JSONDecodeError as e:
                print(f"Error al decodificar JSON de {api_url}: {e}")
                continue
            except Exception as e:
                print(f"Error inesperado con API {api_url}: {e}")
                continue
    except Exception as e:
        print(f"Error general en búsqueda directa: {e}")
    
    # MÉTODO 2: Búsqueda temática
    # Si no se encontraron videos, buscar por temas relacionados
    if not videos_info:
        print(f"Intentando búsqueda por categorías temáticas para: {hashtag}")
        # Expandir las categorías temáticas para aumentar posibilidades de coincidencia
        theme_videos = {
            'meme': [
                "https://www.tiktok.com/@memezar/video/7343252656745408778",
                "https://www.tiktok.com/@dailydoseofmemes.tv/video/7343501842603321627",
                "https://www.tiktok.com/@funnybug/video/7344099352897878278"
            ],
            'funny': [
                "https://www.tiktok.com/@funnyvideosclub/video/7337343809101995307",
                "https://www.tiktok.com/@funnyvid/video/7342847879762906374",
                "https://www.tiktok.com/@funnyreactions/video/7339643715684630827"
            ],
            'gaming': [
                "https://www.tiktok.com/@thegameawards/video/7341242877094362410",
                "https://www.tiktok.com/@gaming/video/7343267050593247494",
                "https://www.tiktok.com/@callofduty/video/7342056807421494574"
            ],
            'music': [
                "https://www.tiktok.com/@music/video/7342876951849264415",
                "https://www.tiktok.com/@taylorswift/video/7335184433138164011",
                "https://www.tiktok.com/@billieeilish/video/7340685753580428590"
            ],
            'dance': [
                "https://www.tiktok.com/@charlidamelio/video/7341795226709909803",
                "https://www.tiktok.com/@addisonre/video/7339809821173342507",
                "https://www.tiktok.com/@justmaiko/video/7337544342720788779"
            ],
            'food': [
                "https://www.tiktok.com/@foodnetwork/video/7343264633030392107",
                "https://www.tiktok.com/@tasty/video/7340327052303255851",
                "https://www.tiktok.com/@gordonramsayofficial/video/7343606700867075371"
            ],
            # Añadir categorías específicas para hashtags populares difíciles de encontrar
            'brainrot': [
                "https://www.tiktok.com/@grantsucks/video/7265741626209035562",
                "https://www.tiktok.com/@smashingjosh/video/7265087875093225798",
                "https://www.tiktok.com/@l.c.m.p/video/7276708487877418282",
                "https://www.tiktok.com/@wavy.duh/video/7298389348218715434"
            ],
            'viral': [
                "https://www.tiktok.com/@khaby.lame/video/7312266556369998086",
                "https://www.tiktok.com/@charlidamelio/video/7312739935253928235",
                "https://www.tiktok.com/@addisonre/video/7317528414632331562"
            ],
            'trending': [
                "https://www.tiktok.com/@heyitspriguel/video/7312740065715192069",
                "https://www.tiktok.com/@andimaybin/video/7323701669915627819",
                "https://www.tiktok.com/@damnnonah/video/7303262765279231274"
            ],
        }
        # Verificar coincidencia exacta primero
        if hashtag_clean in theme_videos:
            for i, url in enumerate(theme_videos[hashtag_clean]):
                videos_info.append({
                    'id': f'themed_{hashtag_clean}_{i}',
                    'url': url,
                    'title': f'Video de {hashtag}',
                    'uploader': 'Creador de TikTok'
                })
            print(f"Encontrados {len(videos_info)} videos específicos para {hashtag}")
        else:
            # Buscar coincidencias parciales en cualquier parte del texto
            for theme_key, videos in theme_videos.items():
                if theme_key in hashtag_clean or hashtag_clean in theme_key:
                    print(f"Encontrada coincidencia parcial con categoría: {theme_key}")
                    for i, url in enumerate(videos):
                        videos_info.append({
                            'id': f'themed_{i}',
                            'url': url,
                            'title': f'Video de {theme_key} relacionado con {hashtag}',
                            'uploader': 'Creador de TikTok'
                        })
                    if videos_info:
                        print(f"Usando {len(videos_info)} videos temáticos relacionados con {theme_key}")
                        break
    # MÉTODO 3: Último recurso - videos genéricos populares
    if not videos_info:
        print(f"No se encontraron videos específicos para el tema: {hashtag}")
        print("Usando videos generales populares (podrían no estar relacionados con el tema)")
        
        # Obtener videos aleatorios del listado general
        import random
        random.shuffle(FALLBACK_VIDEOS)
        fallback_videos = FALLBACK_VIDEOS[:count]
        for i, url in enumerate(fallback_videos):
            videos_info.append({
                'id': f'general_{i}',
                'url': url,
                'title': f'Video popular (tema solicitado: {hashtag})',
                'uploader': 'Creador popular de TikTok'
            })
    print(f"Total de videos encontrados: {len(videos_info)}")
    # Guardar en caché para futuras búsquedas
    if videos_info and use_cache: # Solo guardar si se encontraron videos
        theme_video_registry[hashtag_clean] = videos_info
        try: # Añadir try-except al guardar caché
            with open(THEME_VIDEO_REGISTRY, "wb") as f:
                pickle.dump(theme_video_registry, f)
            print(f"Videos para '{hashtag_clean}' agregados a caché: {len(videos_info)}")
        except Exception as e:
            print(f"Error al guardar caché de videos: {e}")

    return videos_info

# Nueva función para convertir URLs de TikTok al formato de embedez.com
def convert_to_embedez(url):
    """Convierte una URL de TikTok normal al formato de embedez.com para embeds directos."""
    # Verificar si es una URL de TikTok
    if 'tiktok.com' not in url:
        return url
    
    # Reemplazar tiktok.com por tiktokez.com
    return url.replace('tiktok.com', 'tiktokez.com')

# Simplificar la función download_tiktok_video para usar el método embedez
async def download_tiktok_video(url, max_size_mb=8):
    """
    Ahora esta función simplemente retorna la URL convertida para embedez.com
    Mantenemos el fallback a video local en caso de emergencia
    """
    # Definir la ruta del video de fallback
    fallback_video_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "videos", "fallback_video.mp4")
    
    try:
        # Convertir la URL para embedez
        embedez_url = convert_to_embedez(url)
        print(f"Usando embedez para: {url} -> {embedez_url}")
        
        # Devolvemos tanto la URL embedez como None para archivo local
        # Esto permite a las funciones que llaman saber que deben usar el embed en lugar de archivo
        return None, embedez_url
        
    except Exception as e:
        print(f"Error al procesar URL con embedez: {e}")
        # Si algo sale mal, intentar usar video de fallback como último recurso
        if os.path.exists(fallback_video_path):
            print("Usando video de respaldo local debido a error.")
            return fallback_video_path, None
        return None, None

# Tarea periódica para enviar videos aleatorios
@tasks.loop(hours=1)
async def send_random_video():
    global themes
    if not api:
        print("Error: TikTokApi no está configurada correctamente. La tarea no se ejecutará.")
        return
    try:
        if not themes:
            print("No hay temas asignados. La tarea no se ejecutará.")
            return
        theme = random.choice(themes)
        print(f"Seleccionado tema: {theme}")
        videos = await get_tiktok_videos_by_hashtag(theme, count=5)
        if not videos:
            print(f"No se encontraron videos para el tema: {theme}")
            return
        video_info = random.choice(videos)
        video_url = video_info['url']
        print(f"Video seleccionado: {video_url}")
        channel = bot.get_channel(channel_id)
        if (channel is None):
            print("Error: No se pudo encontrar el canal. Verifica el ID del canal.")
            return
        permissions = channel.permissions_for(channel.guild.me)
        if not permissions.send_messages:
            print("Error: El bot no tiene permisos para enviar mensajes en este canal.")
        if not permissions.embed_links:
            print("Advertencia: El bot no tiene permisos para incluir enlaces embebidos.")
                
        # Usar la función modificada
        video_file, embedez_url = await download_tiktok_video(video_url)
        
        if embedez_url:
            # Usar la URL de embedez directamente
            content_msg = f"Aquí tienes un video de {theme}: {embedez_url}"
            await channel.send(content_msg)
            
        elif video_file:
            # Caso de fallback con archivo local
            content_msg = f"⚠️ No se pudo obtener el video de TikTok. Aquí tienes un video de respaldo para **{theme}**."
            await channel.send(
                content=content_msg,
                file=discord.File(video_file)
            )
            
        else:
            # Error total
            await channel.send(f"Aquí tienes un video de {theme}: {video_url}")
            
    except Exception as e:
        print(f"Error al obtener o enviar videos: {e}")
# Comando de aplicación (slash command) para enviar un video aleatorio
@bot.tree.command(name="enviar_video", description="Envía un video aleatorio de TikTok basado en los temas asignados")
async def enviar_video(interaction: discord.Interaction):
    global themes
    # Verificaciones iniciales con respuestas inmediatas
    if not themes:
        await interaction.response.send_message("No hay temas asignados. Usa `_asignar_tema` para añadir algunos.", ephemeral=True)
        return
    # IMPORTANTE: Responder inmediatamente para evitar el error "La aplicación no respondió".
    await interaction.response.defer(thinking=True)
    try:
        # Seleccionar un tema aleatorio
        theme = random.choice(themes)
        print(f"[/enviar_video] Tema seleccionado: {theme}")
        # Informar al usuario
        searching_msg = await interaction.followup.send(f"🔍 Buscando videos de **{theme}**... Por favor espera.")
        # MÉTODO ALTERNATIVO: Usar yt-dlp directamente para obtener videos
        videos = await get_tiktok_videos_by_hashtag(theme, count=5)
        if not videos:
            await interaction.followup.send(f"⚠️ No se encontraron videos para el tema: **{theme}**")
            return
        # Seleccionar un video aleatorio 
        video_info = random.choice(videos)
        video_url = video_info['url']
        print(f"[/enviar_video] Video seleccionado: {video_url}")
        # Informar que se está descargando:
        try:
            await searching_msg.edit(content=f"⬇️ Preparando video de **{theme}**... Por favor espera.")
        except:
            pass  # Ignorar errores de edición
        # Usar la función modificada
        video_file, embedez_url = await download_tiktok_video(video_url)
        
        if embedez_url:
            # Usar la URL de embedez directamente
            content_msg = f"🎬 ¡Listo! Aquí tienes un video de **{theme}**: {embedez_url}"
            await interaction.followup.send(content=content_msg)
            
            # Intentar eliminar el mensaje de búsqueda
            try:
                await searching_msg.delete()
            except:
                pass
                
        elif video_file:
            # Caso de fallback con archivo local
            content_msg = f"⚠️ No se pudo obtener el video de TikTok. Aquí tienes un video de respaldo para **{theme}**."
            await interaction.followup.send(
                content=content_msg,
                file=discord.File(video_file)
            )
            
        else:
            # Error total
            await interaction.followup.send(f"⚠️ No se pudo procesar el video. Aquí está el enlace original: {video_url}")
            
    except Exception as e:
        # Manejar cualquier error de manera segura
        error_msg = str(e)
        print(f"Error crítico en /enviar_video: {error_msg}")
        import traceback
        traceback.print_exc()  # Imprimir traza completa para diagnóstico
        try:
            await interaction.followup.send(f"❌ Error al obtener el video: {error_msg}")
        except:
            # Si ya ha pasado demasiado tiempo, es posible que la interacción ya no sea válida
            channel = interaction.channel
            if channel:
                try:
                    await channel.send(f"❌ Error al procesar el comando de {interaction.user.mention}: {error_msg}")
                except:
                    pass
    
# Agregar un comando alternativo que permita enviar un video directo de TikTok
@bot.tree.command(name="video_directo", description="Envía un video específico de TikTok dado su URL")
async def video_directo(interaction: discord.Interaction, url: str):
    """Comando para enviar un video específico de TikTok usando su URL."""
    # Verificar que la URL sea de TikTok
    if not ('tiktok.com' in url):
        await interaction.response.send_message("❌ Por favor proporciona una URL válida de TikTok.", ephemeral=True)
        return
    # Responder inmediatamente para evitar timeout
    await interaction.response.defer(thinking=True)
    try:
        # Informar al usuario
        searching_msg = await interaction.followup.send(f"⬇️ Preparando video... Por favor espera.")
        
        # Usar nuestra nueva función simplificada
        video_file, embedez_url = await download_tiktok_video(url)
        
        if embedez_url:
            # Usar la URL de embedez directamente
            await interaction.followup.send(f"🎬 ¡Listo! Aquí tienes tu video: {embedez_url}")
            
            # Intentar eliminar el mensaje de búsqueda
            try:
                await searching_msg.delete()
            except:
                pass
                
        elif video_file:
            # Caso de fallback con archivo local
            await interaction.followup.send(
                content="⚠️ No se pudo obtener el embed del video. Usando video de respaldo.",
                file=discord.File(video_file)
            )
            
        else:
            # Error total
            await interaction.followup.send(f"⚠️ No se pudo procesar el video. Aquí está el enlace original: {url}")
            
    except Exception as e:
        error_msg = str(e)
        print(f"Error al descargar el video directo: {error_msg}")
        await interaction.followup.send(f"❌ Error: {error_msg}")
# También añadir la versión con prefijo
@bot.command(name='video_directo')
async def prefix_video_directo(ctx, url: str):
    """Comando con prefijo para enviar un video específico de TikTok."""
    # Evitar procesamiento duplicado
    now = time.time()
    if ctx.message.id in message_timestamps and now - message_timestamps[ctx.message.id] < 5:
        return
    message_timestamps[ctx.message.id] = now
    # Verificar que la URL sea de TikTok
    if not ('tiktok.com' in url):
        await ctx.send("❌ Por favor proporciona una URL válida de TikTok.")
        return
    # Informar al usuario
    loading_msg = await ctx.send("⬇️ Preparando video... Por favor espera.")
    try:
        # Usar nuestra nueva función simplificada
        video_file, embedez_url = await download_tiktok_video(url)
        
        if embedez_url:
            # Usar la URL de embedez directamente
            await ctx.send(f"🎬 ¡Listo! Aquí tienes tu video: {embedez_url}")
            
            # Eliminar el mensaje de carga
            try:
                await loading_msg.delete()
            except:
                pass
                
        elif video_file:
            # Caso de fallback con archivo local
            await ctx.send(
                content="⚠️ No se pudo obtener el embed del video. Usando video de respaldo.",
                file=discord.File(video_file)
            )
            
            # Eliminar el mensaje de carga
            try:
                await loading_msg.delete()
            except:
                pass
                
        else:
            # Error total
            await ctx.send(f"⚠️ No se pudo procesar el video. Aquí está el enlace original: {url}")
    except Exception as e:
        error_msg = str(e)
        await ctx.send(f"❌ Error: {error_msg}")
        print(f"Error en _video_directo: {error_msg}")

# Nuevo comando para precargar videos de temas y guardarlos localmente
@bot.command(name='precargar_videos')
@commands.is_owner()  # Solo el dueño del bot puede usar este comando
async def preload_videos(ctx, theme=None, num_videos=3):
    """Comando para precargar videos de un tema específico o de todos los temas."""
    if not theme and not themes:
        await ctx.send("No hay temas para precargar videos.")
        return
        
    themes_to_process = [theme] if theme else themes
    await ctx.send(f"🔄 Iniciando precarga de videos para {len(themes_to_process)} temas. Esto puede tardar varios minutos...")
    
    total_videos = 0
    for current_theme in themes_to_process:
        try:
            # Buscar sin usar caché para obtener nuevos videos
            videos = await get_tiktok_videos_by_hashtag(current_theme, count=num_videos, use_cache=False)
            
            if not videos:
                await ctx.send(f"⚠️ No se encontraron videos para: {current_theme}")
                continue
                
            await ctx.send(f"✅ Encontrados {len(videos)} videos para {current_theme}")
            total_videos += len(videos)
            
        except Exception as e:
            await ctx.send(f"❌ Error al precargar videos para {current_theme}: {e}")
    
    await ctx.send(f"✅ Precarga completada: {total_videos} videos en total para {len(themes_to_process)} temas")

# Evento cuando el bot está listo
@bot.event
async def on_ready():
    print(f'Bot conectado como {bot.user}')
    try:
        # Sincronizar los comandos de aplicación
        await bot.tree.sync()
        print("Comandos de aplicación sincronizados.")

        # Validar que el bot tiene acceso al canal
        channel = bot.get_channel(channel_id)  # No es necesario convertir nuevamente
        if channel is None:
            print("Error: No se pudo encontrar el canal. Verifica el ID del canal.")
        else:
            print(f"El bot tiene acceso al canal: {channel.name}")

            permissions = channel.permissions_for(channel.guild.me)
            if not permissions.send_messages:
                print("Error: El bot no tiene permisos para enviar mensajes en este canal.")
            if not permissions.embed_links:
                print("Advertencia: El bot no tiene permisos para incluir enlaces embebidos.")

        send_random_video.start()
        clean_timestamps.start()  # Asegurar que esta tarea se inicie
    except Exception as e:
        print(f"Error al iniciar las tareas periódicas: {e}")

# Remover el evento de manejo de errores de cooldown que ya no es necesario
# @bot.event
# async def on_command_error(ctx, error):
#     ...

# Cargar el token desde el archivo .env
token = os.getenv('BOT_TOKEN')

if not token:
    raise ValueError("El token del bot no se ha encontrado. Asegúrate de que el archivo .env contiene 'BOT_TOKEN'.")

if len(token) < 50:
    raise ValueError("El token parece inválido. Verifica que sea correcto.")

bot.run(token)