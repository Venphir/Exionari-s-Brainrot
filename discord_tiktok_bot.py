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
    # Intentar importar PIL para verificar si está instalado
    from PIL import Image
except ImportError:
    print("=== ERROR: Pillow no está instalado ===")
    print("Instagrapi requiere Pillow (PIL) para funcionar.")
    print("Ejecuta este comando para instalar la dependencia:")
    print("pip install Pillow>=8.1.1")
    print("=========================================")
    sys.exit(1)
    
# Ahora que sabemos que PIL está instalado, importar instagrapi
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

# Cargar credenciales de Instagram
INSTAGRAM_USERNAME = os.getenv("INSTAGRAM_USERNAME")
INSTAGRAM_PASSWORD = os.getenv("INSTAGRAM_PASSWORD")

if not INSTAGRAM_USERNAME or not INSTAGRAM_PASSWORD:
    raise ValueError("Las credenciales de Instagram no se encontraron en el archivo .env. Asegúrate de incluir 'INSTAGRAM_USERNAME' y 'INSTAGRAM_PASSWORD'.")

# Directorio para almacenar la sesión de Instagram
SESSION_FILE = os.path.join(CACHE_DIR, "instagram_session.json")

# Inicializar el cliente de Instagram - MOVER LA CONEXIÓN PARA NO BLOQUEAR EL INICIO DEL BOT
ig_client = Client()
instagram_connected = False

# Cargar token de Discord desde variables de entorno
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("El token del bot de Discord no se encontró en el archivo .env. Asegúrate de incluir 'BOT_TOKEN'.")

# Evento cuando el bot está listo
@bot.event
async def on_ready():
    print(f'Bot conectado como {bot.user}')
    try:
        # Sincronizar los comandos de aplicación
        await bot.tree.sync()
        print("Comandos de aplicación sincronizados.")
        
        # Validar que el bot tiene acceso al canal
        global channel_id
        if channel_id:
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
        
        # Iniciar tareas programadas
        send_random_video.start()
        clean_timestamps.start()
        
        # Conectar a Instagram en segundo plano
        bot.loop.create_task(connect_to_instagram())
        
    except Exception as e:
        print(f"Error al inicializar el bot: {e}")
        traceback.print_exc()

# Conectar a Instagram de manera asíncrona para no bloquear el bot
async def connect_to_instagram():
    global ig_client, instagram_connected
    try:
        # Realizar la conexión en una tarea separada para no bloquear el bot
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
    # Verificar si existe una sesión guardada
    if os.path.exists(SESSION_FILE):
        try:
            ig_client.load_settings(SESSION_FILE)
            ig_client.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
            print("Sesión cargada exitosamente desde el archivo.")
            return
        except Exception as e:
            print(f"Error al cargar la sesión: {e}. Iniciando una nueva sesión...")

    # Si no hay sesión o falla la carga, iniciar sesión normalmente
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

    # Guardar la sesión después de un inicio exitoso
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
                return False
            return True
        return False
    except (http_requests.exceptions.RequestException, http_requests.exceptions.Timeout):
        return False

# Función para buscar Instagram Reels por hashtag
async def get_instagram_reels_by_hashtag(hashtag, count=5, use_cache=True):
    global theme_video_registry
    print(f"Buscando Instagram Reels para hashtag: {hashtag}")
    hashtag_clean = hashtag.lstrip('#').lower()
    videos_info = []

    # 1. Intentar usar el caché, pero validar los enlaces
    if use_cache & hashtag_clean in theme_video_registry:
        cached_videos = theme_video_registry.get(hashtag_clean, [])
        valid_videos = []
        for video in cached_videos:
            if await is_valid_instagram_url(video['url']):
                valid_videos.append(video)
            else:
                print(f"Enlace no válido eliminado del caché: {video['url']}")
        if valid_videos:
            print(f"Usando videos en caché para {hashtag_clean}, {len(valid_videos)} disponibles")
            random.shuffle(valid_videos)
            videos_info = valid_videos[:count]
            # Actualizar el caché con solo los enlaces válidos
            theme_video_registry[hashtag_clean] = valid_videos
            try:
                with open(THEME_VIDEO_REGISTRY, "wb") as f:
                    pickle.dump(theme_video_registry, f)
                print(f"Caché actualizado para '{hashtag_clean}' con {len(valid_videos)} videos válidos")
            except Exception as e:
                print(f"Error al actualizar caché: {e}")

    # 2. Si no hay suficientes videos válidos en caché, buscar nuevos usando instagrapi
    if len(videos_info) < count:
        try:
            # Buscar hashtag en Instagram
            hashtag_data = ig_client.hashtag_info(hashtag_clean)
            if not hashtag_data:
                print(f"No se encontró el hashtag: {hashtag_clean}")
                return videos_info

            # Obtener publicaciones recientes del hashtag
            medias = ig_client.hashtag_medias_recent(hashtag_clean, amount=count * 2)
            temp_videos = []
            for media in medias:
                if (media.media_type == 2):  # 2 indica un video (Reel)
                    video_url = f"https://www.instagram.com/reel/{media.code}/"
                    temp_videos.append({
                        'id': media.pk,
                        'url': video_url,
                        'title': media.caption_text[:100] if media.caption_text else f'Reel de {media.user.username}',
                        'uploader': media.user.username
                    })

            # 3. Validar los enlaces encontrados antes de añadirlos
            for video in temp_videos:
                if len(videos_info) >= count:
                    break
                if await is_valid_instagram_url(video['url']):
                    videos_info.append(video)
                    print(f"Enlace válido añadido: {video['url']}")
                else:
                    print(f"Enlace no válido descartado: {video['url']}")

            # 4. Actualizar el caché con los enlaces válidos
            if videos_info and use_cache:
                existing_videos = theme_video_registry.get(hashtag_clean, [])
                all_videos = videos_info + [v for v in existing_videos if v not in videos_info]
                theme_video_registry[hashtag_clean] = all_videos
                try:
                    with open(THEME_VIDEO_REGISTRY, "wb") as f:
                        pickle.dump(theme_video_registry, f)
                    print(f"Reels para '{hashtag_clean}' agregados a caché: {len(videos_info)}")
                except Exception as e:
                    print(f"Error al guardar caché de videos: {e}")
        except Exception as e:
            print(f"Error al buscar Instagram Reels: {e}")
            traceback.print_exc()

    return videos_info[:count]

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
@bot.tree.command(name="asignar_tema", description="Asigna uno o más temas/hashtags para buscar Instagram Reels")
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
            "➡️ Envía un Instagram Reel aleatorio basado en los temas asignados.\n"
            "➡️ El comando slash aparece en el menú al escribir `/`\n\n"
            "**`/video_directo`** o **`_video_directo`**\n"
            "➡️ Envía un Reel específico dado su URL de Instagram.\n"
            "➡️ Ejemplo: `/video_directo url:https://www.instagram.com/reel/ABC123/`"
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
            "• El bot usa enlaces directos para mostrar Reels en Discord."
        ),
        inline=False
    )
    embed.set_footer(text=f"Bot Instagram Reels • Solicitado por {interaction.user.name}", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
    embed.timestamp = discord.utils.utcnow()
    await interaction.response.send_message(embed=embed)

# Comando con prefijo para enviar un video
@bot.command(name='enviar_video')
async def prefix_send_video(ctx):
    global themes, instagram_connected
    now = time.time()
    if ctx.message.id in message_timestamps and now - message_timestamps[ctx.message.id] < 5:
        return
    message_timestamps[ctx.message.id] = now
    
    if not themes:
        await ctx.send("No hay temas asignados. Usa `_asignar_tema` para añadir algunos.")
        return
    
    if not instagram_connected:
        await ctx.send("⌛ La conexión con Instagram aún está en proceso. Por favor espera unos segundos e intenta nuevamente.")
        return
    
    loading_msg = await ctx.send("🔍 Buscando un Reel aleatorio... Por favor espera.")
    try:
        # Seleccionar un tema aleatorio
        theme = random.choice(themes)
        print(f"[_enviar_video] Tema seleccionado: {theme}")
        
        # Buscar reels para el tema
        await loading_msg.edit(content=f"🔍 Buscando Reels para **{theme}**... Por favor espera.")
        videos = await get_instagram_reels_by_hashtag(theme, count=5)
        
        if not videos:
            await ctx.send(f"⚠️ No se encontraron Reels para el tema: **{theme}**. Intenta con otro tema.")
            try:
                await loading_msg.delete()
            except:
                pass
            return
            
        # Seleccionar un video aleatorio
        video_info = random.choice(videos)
        video_url = video_info['url']
        
        # Enviar el video
        content_msg = f"📱 Aquí tienes un Instagram Reel de **{theme}**:\n{video_url}"
        await ctx.send(content=content_msg)
        
        # Eliminar mensaje de carga
        try:
            await loading_msg.delete()
        except:
            pass
            
    except Exception as e:
        error_msg = str(e)
        await ctx.send(f"❌ Error al obtener el Reel: {error_msg}")
        print(f"Error en _enviar_video: {error_msg}")
        traceback.print_exc()

# Comando slash para enviar un video
@bot.tree.command(name="enviar_video", description="Envía un Instagram Reel aleatorio basado en los temas asignados")
async def slash_send_video(interaction: discord.Interaction):
    global themes, instagram_connected
    
    if not themes:
        await interaction.response.send_message("No hay temas asignados. Usa `/asignar_tema` para añadir algunos.", ephemeral=True)
        return
    
    if not instagram_connected:
        await interaction.response.send_message("⌛ La conexión con Instagram aún está en proceso. Por favor espera unos segundos e intenta nuevamente.", ephemeral=True)
        return
    
    # Responder inmediatamente para evitar timeout
    await interaction.response.defer(thinking=True)
    
    try:
        # Seleccionar tema aleatorio
        theme = random.choice(themes)
        print(f"[/enviar_video] Tema seleccionado: {theme}")
        
        # Informar al usuario
        searching_msg = await interaction.followup.send(f"🔍 Buscando Reels de **{theme}**... Por favor espera.")
        
        # Buscar videos
        videos = await get_instagram_reels_by_hashtag(theme, count=5)
        
        if not videos:
            await interaction.followup.send(f"⚠️ No se encontraron Reels para el tema: **{theme}**. Intenta con otro tema.")
            return
            
        # Seleccionar video aleatorio
        video_info = random.choice(videos)
        video_url = video_info['url']
        
        # Enviar el video
        content_msg = f"📱 Aquí tienes un Instagram Reel de **{theme}**:\n{video_url}"
        await interaction.followup.send(content=content_msg)
        
        # Eliminar mensaje de búsqueda
        try:
            await searching_msg.delete()
        except:
            pass
            
    except Exception as e:
        error_msg = str(e)
        await interaction.followup.send(f"❌ Error al obtener el Reel: {error_msg}")
        print(f"Error en /enviar_video: {error_msg}")
        traceback.print_exc()

# Comando para enviar un Reel específico
@bot.tree.command(name="video_directo", description="Envía un Reel específico dado su URL de Instagram")
async def video_directo(interaction: discord.Interaction, url: str):
    if 'instagram.com' not in url:
        await interaction.response.send_message("❌ Por favor proporciona una URL válida de Instagram Reels.", ephemeral=True)
        return
        
    await interaction.response.defer(thinking=True)
    
    try:
        # Verificar si el enlace es válido
        searching_msg = await interaction.followup.send("⬇️ Verificando enlace... Por favor espera.")
        
        is_valid = await is_valid_instagram_url(url)
        if not is_valid:
            await interaction.followup.send("❌ El enlace proporcionado no es válido o el Reel no está disponible.")
            try:
                await searching_msg.delete()
            except:
                pass
            return
            
        # Si es válido, enviarlo
        await interaction.followup.send(f"📱 Aquí tienes tu Reel de Instagram: {url}")
        
        # Eliminar mensaje de búsqueda
        try:
            await searching_msg.delete()
        except:
            pass
            
    except Exception as e:
        error_msg = str(e)
        await interaction.followup.send(f"❌ Error al procesar el Reel: {error_msg}")
        print(f"Error en video_directo: {error_msg}")

# Comando con prefijo para enviar un Reel específico
@bot.command(name='video_directo')
async def prefix_video_directo(ctx, url: str):
    now = time.time()
    if ctx.message.id in message_timestamps and now - message_timestamps[ctx.message.id] < 5:
        return
    message_timestamps[ctx.message.id] = now
    
    if 'instagram.com' not in url:
        await ctx.send("❌ Por favor proporciona una URL válida de Instagram Reels.")
        return
        
    # Informar al usuario
    loading_msg = await ctx.send("⬇️ Verificando enlace... Por favor espera.")
    
    try:
        # Verificar si el enlace es válido
        is_valid = await is_valid_instagram_url(url)
        if not is_valid:
            await ctx.send("❌ El enlace proporcionado no es válido o el Reel no está disponible.")
            try:
                await loading_msg.delete()
            except:
                pass
            return
                
        # Si es válido, enviarlo
        await ctx.send(f"📱 Aquí tienes tu Reel de Instagram: {url}")
        
        # Eliminar mensaje de carga
        try:
            await loading_msg.delete()
        except:
            pass
            
    except Exception as e:
        error_msg = str(e)
        await ctx.send(f"❌ Error: {error_msg}")
        print(f"Error en _video_directo: {error_msg}")

# Tarea periódica para enviar videos aleatorios
@tasks.loop(hours=12)  # Cada 12 horas - ajusta según necesites
async def send_random_video():
    global themes, instagram_connected, channel_id
    
    if not themes or not instagram_connected or not channel_id:
        print("No se puede ejecutar la tarea automática: faltan temas, conexión a Instagram o ID del canal.")
        return
        
    try:
        # Obtener el canal
        channel = bot.get_channel(channel_id)
        if not channel:
            print(f"No se pudo encontrar el canal con ID {channel_id}")
            return
            
        # Seleccionar un tema aleatorio
        theme = random.choice(themes)
        print(f"[Tarea automática] Tema seleccionado: {theme}")
        
        # Buscar Reels
        videos = await get_instagram_reels_by_hashtag(theme, count=5)
        if not videos:
            print(f"No se encontraron Reels para el tema: {theme}")
            return
            
        # Seleccionar uno aleatoriamente
        video_info = random.choice(videos)
        video_url = video_info['url']
        
        # Enviar al canal
        await channel.send(f"📱 Reel automático de **{theme}**:\n{video_url}")
        print(f"Reel enviado automáticamente para el tema: {theme}")
        
    except Exception as e:
        print(f"Error en la tarea automática: {e}")
        traceback.print_exc()

# Tarea para limpiar mensajes temporales
@tasks.loop(minutes=5)
async def clean_timestamps():
    now = time.time()
    for msg_id in list(message_timestamps.keys()):
        if now - message_timestamps[msg_id] > 600:  # 10 minutos
            del message_timestamps[msg_id]

# IMPORTANTE: Iniciar el bot al final del archivo
if __name__ == "__main__":
    try:
        print("Iniciando bot de Discord...")
        bot.run(BOT_TOKEN)
    except Exception as e:
        print(f"Error fatal al iniciar el bot: {e}")
        traceback.print_exc()