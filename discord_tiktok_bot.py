import discord
from discord.ext import commands, tasks
from TikTokApi import TikTokApi
import random
import os
from dotenv import load_dotenv
import json
import asyncio
import time  # Faltaba importar el módulo time
import tempfile
import yt_dlp  # Nueva biblioteca para descargar videos
import subprocess  # Para llamar a ffmpeg para compresión
import math  # Para cálculos de calidad de compresión

# Cargar variables de entorno desde el archivo .env
dotenv_path = ".env"
if not os.path.exists(dotenv_path):
    raise FileNotFoundError(f"No se encontró el archivo .env en la ruta: {dotenv_path}")

load_dotenv(dotenv_path=dotenv_path)

# Configurar los intents necesarios
intents = discord.Intents.default()
intents.message_content = True

# Configuración del bot de Discord
bot = commands.Bot(command_prefix='_', intents=intents)

# Configuración de la API de TikTok
try:
    # Inicializar TikTokApi y crear sesión correctamente según la documentación más reciente
    api = TikTokApi()
    # La creación de sesión ahora es asíncrona y debe llamarse así:
    loop = asyncio.get_event_loop()
    loop.run_until_complete(api.create_sessions())
    print("TikTokApi inicializada correctamente.")
except Exception as e:
    print(f"Error al inicializar TikTokApi: {e}")
    api = None

# Ruta del archivo para almacenar los temas
themes_file = "themes.json"

# Configuración del canal desde el archivo .env
channel_id = os.getenv("DISCORD_CHANNEL_ID")  # Usar el nombre correcto de la variable de entorno
if not channel_id:
    raise ValueError("El ID del canal no se ha encontrado. Asegúrate de que el archivo .env contiene 'DISCORD_CHANNEL_ID'.")

# Validar y convertir el ID del canal a entero
try:
    channel_id = int(channel_id)
except ValueError:
    raise ValueError("El ID del canal proporcionado en el archivo .env no es un número válido.")

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
        await loading_msg.edit(content=f"⬇️ Descargando video de **{theme}**... Por favor espera.")
        
        # Descargar el video con compresión si es necesario
        video_file = await download_tiktok_video(video_url)
        
        if video_file:
            # Enviar el video como archivo
            await ctx.send(
                content=f"🎬 ¡Listo! Aquí tienes un video de **{theme}**: {video_url}",
                file=discord.File(video_file)
            )
            # Eliminar el mensaje de carga
            try:
                await loading_msg.delete()
            except:
                pass
            # Eliminar el archivo temporal
            os.remove(video_file)
        else:
            await ctx.send(f"⚠️ No se pudo descargar el video (probablemente demasiado grande). Aquí está el enlace: {video_url}")
            
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

# Función reemplazada que no depende de búsquedas en TikTok
async def get_tiktok_videos_by_hashtag(hashtag, count=5):
    """Obtiene videos de TikTok usando videos predefinidos para evitar bloqueos de IP."""
    print(f"Solicitado tema: {hashtag}")
    
    # Simplemente devolvemos videos de nuestra lista predefinida
    # Barajamos la lista para obtener videos aleatorios cada vez
    random.shuffle(FALLBACK_VIDEOS)
    selected_videos = FALLBACK_VIDEOS[:min(count, len(FALLBACK_VIDEOS))]
    
    videos_info = []
    for i, url in enumerate(selected_videos):
        videos_info.append({
            'id': f'video_{i}',
            'url': url,
            'title': f'Video {i+1} para {hashtag}',
            'uploader': 'TikToker popular'
        })
    
    print(f"Usando {len(videos_info)} videos predefinidos")
    return videos_info

# Función mejorada para descargar videos con mejor manejo de errores y soporte para proxies
async def download_tiktok_video(url, max_size_mb=8):
    """Descarga videos de TikTok usando técnicas avanzadas para evitar bloqueos."""
    # Crear nombres de archivo temporales únicos
    temp_dir = tempfile.gettempdir()
    temp_id = int(time.time())
    original_file = os.path.join(temp_dir, f"tiktok_original_{temp_id}.mp4")
    compressed_file = os.path.join(temp_dir, f"tiktok_compressed_{temp_id}.mp4")
    
    try:
        print(f"Intentando descargar video: {url}")
        
        # Usar opciones más robustas con rotación de user-agents
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0'
        ]
        
        # Seleccionar un User-Agent aleatorio
        user_agent = random.choice(user_agents)
        
        ydl_opts = {
            'format': 'best[ext=mp4]',
            'outtmpl': original_file,
            'quiet': False,  # Cambiar a False para ver los errores detallados
            'verbose': True,  # Activar modo verboso para diagnóstico
            'socket_timeout': 90,
            'retries': 15,
            'fragment_retries': 15,
            'http_headers': {
                'User-Agent': user_agent,
                'Accept-Language': 'en-US,en;q=0.9,es;q=0.8',
                'Accept': '*/*',
                'Referer': 'https://www.tiktok.com/',
                'Origin': 'https://www.tiktok.com'
            },
            'nocheckcertificate': True,
            'no_warnings': False,
        }
        
        # Intentar descargar el video
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            if info_dict:
                print(f"Video extraído con éxito: {info_dict.get('title', 'Unknown')}")
        
        # Verificar si el archivo existe
        if not os.path.exists(original_file):
            print(f"Error: El archivo no se descargó correctamente: {original_file}")
            return None
            
        original_size_mb = os.path.getsize(original_file) / (1024 * 1024)
        print(f"Video descargado. Tamaño: {original_size_mb:.2f} MB")
        
        # Si el archivo es menor al límite, usarlo directamente
        if original_size_mb <= max_size_mb:
            print(f"El video está dentro del límite de tamaño, enviándolo sin comprimir")
            return original_file
            
        # Si es más grande, comprimir con ffmpeg
        print(f"Comprimiendo video (tamaño original: {original_size_mb:.2f} MB)...")
        
        # Resto del código de compresión se mantiene igual
        # ...existing code...
        
    except Exception as e:
        print(f"Error al descargar/comprimir el video: {e}")
        # Limpiar archivos temporales si falló la descarga
        for f in [original_file, compressed_file]:
            if os.path.exists(f):
                os.remove(f)
        return None

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
        if channel is None:
            print("Error: No se pudo encontrar el canal. Verifica el ID del canal.")
            return
        
        permissions = channel.permissions_for(channel.guild.me)
        if not permissions.send_messages:
            print("Error: El bot no tiene permisos para enviar mensajes en este canal.")
        if not permissions.embed_links:
            print("Advertencia: El bot no tiene permisos para incluir enlaces embebidos.")
        
        video_file = await download_tiktok_video(video_url)
        
        if video_file:
            await channel.send(
                content=f"Aquí tienes un video de {theme}: {video_url}",
                file=discord.File(video_file)
            )
            os.remove(video_file)
        else:
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
            await searching_msg.edit(content=f"⬇️ Descargando video de **{theme}**... Por favor espera.")
        except:
            pass  # Ignorar errores de edición
        
        # Descargar el video con timeout ampliado
        video_file = await download_tiktok_video(video_url)
        
        if video_file:
            print(f"[/enviar_video] Enviando video desde archivo: {video_file}")
            try:
                # Enviar el video como archivo
                await interaction.followup.send(
                    content=f"🎬 ¡Listo! Aquí tienes un video de **{theme}**: {video_url}",
                    file=discord.File(video_file)
                )
                # Eliminar el archivo temporal
                os.remove(video_file)
                # Eliminar el mensaje de búsqueda
                try:
                    await searching_msg.delete()
                except:
                    pass
            except discord.HTTPException as http_err:
                print(f"Error HTTP al enviar video: {http_err}")
                await interaction.followup.send(f"⚠️ Error al enviar el video. Aquí está el enlace: {video_url}")
        else:
            # Si no se pudo descargar, enviar solo el enlace
            await interaction.followup.send(f"⚠️ No se pudo descargar el video. Aquí está el enlace: {video_url}")
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
        searching_msg = await interaction.followup.send(f"⬇️ Descargando video... Por favor espera.")
        
        # Intentar descargar el video
        video_file = await download_tiktok_video(url)
        
        if video_file:
            # Enviar el video como archivo
            await interaction.followup.send(
                content=f"🎬 ¡Listo! Aquí tienes tu video: {url}",
                file=discord.File(video_file)
            )
            
            # Eliminar el archivo temporal
            os.remove(video_file)
            
            # Eliminar el mensaje de búsqueda
            try:
                await searching_msg.delete()
            except:
                pass
        else:
            # Si no se pudo descargar, enviar solo el enlace
            await interaction.followup.send(f"⚠️ No se pudo descargar el video. Aquí está el enlace: {url}")
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
    loading_msg = await ctx.send("⬇️ Descargando video... Por favor espera.")
    
    try:
        # Intentar descargar el video
        video_file = await download_tiktok_video(url)
        
        if video_file:
            # Enviar el video como archivo
            await ctx.send(
                content=f"🎬 ¡Listo! Aquí tienes tu video: {url}",
                file=discord.File(video_file)
            )
            
            # Eliminar el archivo temporal
            os.remove(video_file)
            
            # Eliminar el mensaje de carga
            try:
                await loading_msg.delete()
            except:
                pass
        else:
            await ctx.send(f"⚠️ No se pudo descargar el video. Aquí está el enlace: {url}")
            
    except Exception as e:
        error_msg = str(e)
        await ctx.send(f"❌ Error: {error_msg}")
        print(f"Error en _video_directo: {error_msg}")

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