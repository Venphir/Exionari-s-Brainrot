# Standard library imports
import os
import json
import time
import random
import pickle
import asyncio  # Python's built-in async library

# Third-party imports
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
import requests as http_requests

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

# Ruta del archivo para almacenar los temas
themes_file = "themes.json"

# Configuración del canal desde el archivo .env
try:
    channel_id_str = os.getenv("DISCORD_CHANNEL_ID")
    if not channel_id_str:
        print("⚠️ ADVERTENCIA: ID del canal no encontrado en .env")
        channel_id = None
    else:
        channel_id = int(channel_id_str)
        print(f"Canal configurado: {channel_id}")
except ValueError:
    print(f"⚠️ ERROR: El ID del canal '{channel_id_str}' no es un número válido")
    channel_id = None

# Estrategia para evitar comandos duplicados
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

# Función para guardar los temas en el archivo
def save_themes():
    with open(themes_file, "w", encoding="utf-8") as f:
        json.dump(themes, f, ensure_ascii=False, indent=4)
    print("Temas guardados correctamente.")

# Lista para almacenar los temas asignados
themes = []
load_themes()

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
        await ctx.send("Por favor, proporciona al menos un tema válido. Los temas vacíos no son permitidos.")
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
@bot.tree.command(name="asignar_tema", description="Asigna uno o más temas/hashtags para buscar videos de TikTok")
async def slash_assign_theme(interaction: discord.Interaction, temas: str):
    global themes
    args = temas.split()
    new_themes = list(set(filter(None, args)))
    if not new_themes:
        await interaction.response.send_message("Por favor, proporciona al menos un tema válido. Los temas vacíos no son permitidos.", ephemeral=True)
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
    embed.add_field(
        name="🎬 Videos de TikTok",
        value=(
            "**`/enviar_video`** o **`_enviar_video`**\n"
            "➡️ Envía un video aleatorio de TikTok basado en los temas asignados.\n"
            "➡️ El comando slash aparece en el menú al escribir `/`\n\n"
            "**`/video_directo`** o **`_video_directo`**\n"
            "➡️ Envía un video específico dado su URL de TikTok.\n"
            "➡️ Ejemplo: `/video_directo url:https://www.tiktok.com/@user/video/123`"
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
            "• Puedes usar comandos con barra diagonal (`/`) o con prefijo (`_`).\n"
            "• Los temas asignados se guardan automáticamente.\n"
            "• El bot usa embedez para mostrar videos directamente en Discord."
        ),
        inline=False
    )
    embed.set_footer(text=f"Bot TikTok • Solicitado por {interaction.user.name}", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
    embed.timestamp = discord.utils.utcnow()
    await interaction.response.send_message(embed=embed)

# Comando con prefijo para enviar un video
@bot.command(name='enviar_video')
async def prefix_send_video(ctx):
    global themes
    now = time.time()
    if ctx.message.id in message_timestamps and now - message_timestamps[ctx.message.id] < 5:
        return
    message_timestamps[ctx.message.id] = now
    if not themes:
        await ctx.send("No hay temas asignados. Usa `_asignar_tema` para añadir algunos.")
        return
    loading_msg = await ctx.send("🔍 Buscando un video aleatorio... Por favor espera.")
    try:
        theme = random.choice(themes)
        print(f"[_enviar_video] Tema seleccionado: {theme}")
        videos = await get_tiktok_videos_by_hashtag(theme, count=5)
        if not videos:
            await ctx.send(f"⚠️ No se encontraron videos para el tema: **{theme}**")
            return
        video_info = random.choice(videos)
        video_url = video_info['url']
        print(f"[_enviar_video] Video seleccionado: {video_url}")
        await loading_msg.edit(content=f"⬇️ Preparando video de **{theme}**... Por favor espera.")
        embedez_url = convert_to_embedez(video_url)
        content_msg = f"🎬 Aquí tienes un video de **{theme}**: {embedez_url}"
        await ctx.send(content=content_msg)
        try:
            await loading_msg.delete()
        except:
            pass
    except Exception as e:
        error_msg = str(e)
        await ctx.send(f"❌ Error al obtener el video: {error_msg}")
        print(f"Error en _enviar_video: {error_msg}")

# Comando con prefijo para ayuda
@bot.command(name='ayuda')
async def prefix_help_command(ctx):
    now = time.time()
    if ctx.message.id in message_timestamps and now - message_timestamps[ctx.message.id] < 5:
        return
    message_timestamps[ctx.message.id] = now
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
    embed.add_field(
        name="🎬 Videos de TikTok",
        value=(
            "**`/enviar_video`** o **`_enviar_video`**\n"
            "➡️ Envía un video aleatorio de TikTok basado en los temas asignados.\n"
            "➡️ El comando slash aparece en el menú al escribir `/`\n\n"
            "**`/video_directo`** o **`_video_directo`**\n"
            "➡️ Envía un video específico dado su URL de TikTok.\n"
            "➡️ Ejemplo: `/video_directo url:https://www.tiktok.com/@user/video/123`"
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
            "• Puedes usar comandos con barra diagonal (`/`) o con prefijo (`_`).\n"
            "• Los temas asignados se guardan automáticamente.\n"
            "• El bot usa embedez para mostrar videos directamente en Discord."
        ),
        inline=False
    )
    embed.set_footer(text=f"Bot TikTok • Solicitado por {ctx.author.name}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
    embed.timestamp = discord.utils.utcnow()
    await ctx.send(embed=embed)

# Función para convertir URLs de TikTok al formato de embedez.com
def convert_to_embedez(url):
    if 'tiktok.com' not in url:
        return url
    return url.replace('tiktok.com', 'tiktokez.com')

# Tarea periódica para enviar videos aleatorios
@tasks.loop(hours=1)
async def send_random_video():
    global themes
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
    if channel is None:
        print("Error: No se pudo encontrar el canal. Verifica el ID del canal.")
        return
    permissions = channel.permissions_for(channel.guild.me)
    if not permissions.send_messages:
        print("Error: El bot no tiene permisos para enviar mensajes en este canal.")
        return
    embedez_url = convert_to_embedez(video_url)
    content_msg = f"Aquí tienes un video de {theme}: {embedez_url}"
    await channel.send(content_msg)

# Comando de aplicación para enviar un video aleatorio
@bot.tree.command(name="enviar_video", description="Envía un video aleatorio de TikTok basado en los temas asignados")
async def enviar_video(interaction: discord.Interaction):
    global themes
    if not themes:
        await interaction.response.send_message("No hay temas asignados. Usa `_asignar_tema` para añadir algunos.", ephemeral=True)
        return
    await interaction.response.defer(thinking=True)
    try:
        theme = random.choice(themes)
        print(f"[/enviar_video] Tema seleccionado: {theme}")
        searching_msg = await interaction.followup.send(f"🔍 Buscando videos de **{theme}**... Por favor espera.")
        videos = await get_tiktok_videos_by_hashtag(theme, count=5)
        if not videos:
            await interaction.followup.send(f"⚠️ No se encontraron videos para el tema: **{theme}**")
            return
        video_info = random.choice(videos)
        video_url = video_info['url']
        print(f"[/enviar_video] Video seleccionado: {video_url}")
        try:
            await searching_msg.edit(content=f"⬇️ Preparando video de **{theme}**... Por favor espera.")
        except:
            pass
        embedez_url = convert_to_embedez(video_url)
        content_msg = f"🎬 ¡Listo! Aquí tienes un video de **{theme}**: {embedez_url}"
        await interaction.followup.send(content=content_msg)
        try:
            await searching_msg.delete()
        except:
            pass
    except Exception as e:
        error_msg = str(e)
        print(f"Error crítico en /enviar_video: {error_msg}")
        import traceback
        traceback.print_exc()
        await interaction.followup.send(f"❌ Error al obtener el video: {error_msg}")

# Comando de aplicación para enviar un video directo
@bot.tree.command(name="video_directo", description="Envía un video específico de TikTok dado su URL")
async def video_directo(interaction: discord.Interaction, url: str):
    if 'tiktok.com' not in url:
        await interaction.response.send_message("❌ Por favor proporciona una URL válida de TikTok.", ephemeral=True)
        return
    await interaction.response.defer(thinking=True)
    try:
        searching_msg = await interaction.followup.send(f"⬇️ Preparando video... Por favor espera.")
        embedez_url = convert_to_embedez(url)
        await interaction.followup.send(f"🎬 ¡Listo! Aquí tienes tu video: {embedez_url}")
        try:
            await searching_msg.delete()
        except:
            pass
    except Exception as e:
        error_msg = str(e)
        print(f"Error al procesar video directo: {error_msg}")
        await interaction.followup.send(f"❌ Error: {error_msg}")

# Comando con prefijo para enviar un video directo
@bot.command(name='video_directo')
async def prefix_video_directo(ctx, url: str):
    now = time.time()
    if ctx.message.id in message_timestamps and now - message_timestamps[ctx.message.id] < 5:
        return
    message_timestamps[ctx.message.id] = now
    if 'tiktok.com' not in url:
        await ctx.send("❌ Por favor proporciona una URL válida de TikTok.")
        return
    loading_msg = await ctx.send("⬇️ Preparando video... Por favor espera.")
    try:
        embedez_url = convert_to_embedez(url)
        await ctx.send(f"🎬 ¡Listo! Aquí tienes tu video: {embedez_url}")
        try:
            await loading_msg.delete()
        except:
            pass
    except Exception as e:
        error_msg = str(e)
        await ctx.send(f"❌ Error: {error_msg}")
        print(f"Error en _video_directo: {error_msg}")

# Limpieza periódica de timestamps antiguos
@tasks.loop(minutes=5)
async def clean_timestamps():
    now = time.time()
    for msg_id in list(message_timestamps.keys()):
        if now - message_timestamps[msg_id] > 600:  # 10 minutos
            del message_timestamps[msg_id]

# Función para buscar videos por hashtag (mantenida de tu código)
async def get_tiktok_videos_by_hashtag(hashtag, count=5, use_cache=True):
    global theme_video_registry
    print(f"Buscando videos para hashtag: {hashtag}")
    hashtag_clean = hashtag.lstrip('#').lower()
    videos_info = []

    if use_cache and hashtag_clean in theme_video_registry:
        cached_videos = theme_video_registry.get(hashtag_clean, [])
        if cached_videos:
            print(f"Usando videos en caché para {hashtag_clean}, {len(cached_videos)} disponibles")
            random.shuffle(cached_videos)
            return cached_videos[:count]

    try:
        urls_to_try = [
            f"https://tiktokder.com/api/short/search?keyword={hashtag_clean}&count=10",
            f"https://www.tiktok.com/api/search/general/full/?keyword={hashtag_clean}&is_filter_word=0&from_page=search",
            f"https://www.tikwm.com/api/feed/search?keywords={hashtag_clean}"
        ]
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
        for api_url in urls_to_try:
            try:
                response = http_requests.get(api_url, headers=headers, timeout=15)
                response.raise_for_status()
                data = response.json()
                if "data" in data and isinstance(data["data"], list):
                    for item in data["data"][:count*2]:
                        if item.get('type') == 'video' and 'item' in item:
                            item_data = item['item']
                            if 'id' in item_data and 'author' in item_data:
                                username = item_data['author'].get('uniqueId', 'tiktok_user')
                                video_url = f"https://www.tiktok.com/@{username}/video/{item_data['id']}"
                                videos_info.append({
                                    'id': item_data['id'],
                                    'url': video_url,
                                    'title': item_data.get('desc', f'Video de {username}'),
                                    'uploader': username
                                })
                elif "videos" in data:
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
                    for video in data["items"][:count*2]:
                        if 'id' in video and 'author' in video:
                            video_url = video.get('share_url', f"https://www.tiktok.com/@{video['author']['unique_id']}/video/{video['id']}")
                            videos_info.append({
                                'id': video['id'],
                                'url': video_url,
                                'title': video.get('title', 'Video de TikTok'),
                                'uploader': video['author'].get('unique_id', 'TikTok user')
                            })
                if len(videos_info) >= count:
                    break
            except http_requests.exceptions.RequestException as e:
                print(f"Error de red/HTTP con API {api_url}: {e}")
                continue
            except json.JSONDecodeError as e:
                print(f"Error al decodificar JSON de {api_url}: {e}")
                continue
            except Exception as e:
                print(f"Error inesperado con API {api_url}: {e}")
                continue
    except Exception as e:
        print(f"Error general en búsqueda directa: {e}")

    if videos_info and use_cache:
        theme_video_registry[hashtag_clean] = videos_info
        try:
            with open(THEME_VIDEO_REGISTRY, "wb") as f:
                pickle.dump(theme_video_registry, f)
            print(f"Videos para '{hashtag_clean}' agregados a caché: {len(videos_info)}")
        except Exception as e:
            print(f"Error al guardar caché de videos: {e}")

    return videos_info[:count] if videos_info else []

# Evento cuando el bot está listo
@bot.event
async def on_ready():
    print(f'Bot conectado como {bot.user}')
    try:
        await bot.tree.sync()
        print("Comandos de aplicación sincronizados.")
        channel = bot.get_channel(channel_id)
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
        clean_timestamps.start()
    except Exception as e:
        print(f"Error al iniciar las tareas periódicas: {e}")

# Cargar el token desde el archivo .env
token = os.getenv('BOT_TOKEN')

if not token:
    raise ValueError("El token del bot no se ha encontrado. Asegúrate de que el archivo .env contiene 'BOT_TOKEN'.")

if len(token) < 50:
    raise ValueError("El token parece inválido. Verifica que sea correcto.")

bot.run(token)