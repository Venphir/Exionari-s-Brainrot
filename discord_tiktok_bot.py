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

# Comando de ayuda mejorado y profesional
@bot.command(name='ayuda')
async def help_command(ctx):
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
            "**`_asignar_tema [temas...]`**\n"
            "➡️ Asigna uno o más temas (hashtags) para buscar videos.\n"
            "➡️ Ejemplo: `_asignar_tema #meme #funny`\n\n"
            
            "**`_eliminar_tema [tema]`**\n"
            "➡️ Elimina un tema de la lista.\n"
            "➡️ Ejemplo: `_eliminar_tema #meme`\n\n"
            
            "**`_ver_temas`**\n"
            "➡️ Muestra los temas actualmente asignados.\n"
            "➡️ Ejemplo: `_ver_temas`"
        ),
        inline=False
    )
    
    # Comandos para videos
    embed.add_field(
        name="🎬 Videos de TikTok",
        value=(
            "**`/enviar_video`**\n"
            "➡️ Envía un video aleatorio de TikTok basado en los temas asignados.\n"
            "➡️ Este es un comando slash y aparece en el menú al escribir `/`"
        ),
        inline=False
    )
    
    # Comandos de ayuda
    embed.add_field(
        name="❓ Ayuda",
        value=(
            "**`_ayuda`**\n"
            "➡️ Muestra este mensaje de ayuda.\n"
            "➡️ Ejemplo: `_ayuda`"
        ),
        inline=False
    )
    
    # Nota adicional
    embed.add_field(
        name="📝 Notas",
        value=(
            "• Los temas asignados se guardan automáticamente y no se pierden al reiniciar el bot.\n"
            "• Para que el bot funcione correctamente, debe tener permisos para enviar mensajes y enlaces."
        ),
        inline=False
    )
    
    # Pie de página
    embed.set_footer(text=f"Bot TikTok • Solicitado por {ctx.author.name}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
    
    # Agregar timestamp
    embed.timestamp = discord.utils.utcnow()
    
    await ctx.send(embed=embed)

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
        
        # Obtener videos (puede tardar)
        hashtag_data = api.hashtag(name=theme.lstrip('#'))
        videos = []
        async for video in hashtag_data.videos(count=10):
            videos.append(video)
            
        if not videos:
            await ctx.send(f"⚠️ No se encontraron videos para el tema: **{theme}**")
            return

        # Seleccionar un video aleatorio
        video = random.choice(videos)
        video_url = f"https://www.tiktok.com/@{video.author.username}/video/{video.id}"
        
        # Actualizar el mensaje
        await loading_msg.edit(content=f"⬇️ Descargando video de **{theme}**... Por favor espera.")
        
        # Descargar el video
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
            await ctx.send(f"⚠️ No se pudo descargar el video. Aquí está el enlace: {video_url}")
            
    except Exception as e:
        error_msg = str(e)
        await ctx.send(f"❌ Error al obtener el video: {error_msg}")
        print(f"Error en _enviar_video: {error_msg}")

# Actualizar el comando de ayuda con prefijo para mostrar ambas opciones
@bot.command(name='ayuda')
async def help_command(ctx):
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

# Función auxiliar para descargar un video de TikTok
async def download_tiktok_video(url):
    # Crear un nombre de archivo temporal único
    temp_dir = tempfile.gettempdir()
    temp_file = os.path.join(temp_dir, f"tiktok_video_{int(time.time())}.mp4")
    
    # Opciones para yt-dlp
    ydl_opts = {
        'format': 'mp4',
        'outtmpl': temp_file,
        'quiet': True,
    }
    
    # Descargar el video
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        # Verificar si el archivo es demasiado grande (límite de Discord: 8MB)
        if os.path.getsize(temp_file) > 8 * 1024 * 1024:
            print(f"Video demasiado grande para enviar: {os.path.getsize(temp_file) / (1024 * 1024):.2f} MB")
            os.remove(temp_file)
            return None
            
        return temp_file
    except Exception as e:
        print(f"Error al descargar el video: {e}")
        # Limpiar archivos temporales si falló la descarga
        if os.path.exists(temp_file):
            os.remove(temp_file)
        return None

# Tarea periódica para enviar videos aleatorios
@tasks.loop(hours=1)
async def send_random_video():
    global themes
    if not api:
        print("Error: TikTokApi no está configurada correctamente. La tarea no se ejecutará.")
        return

    if not themes:
        print("No hay temas asignados. La tarea no se ejecutará.")
        return

    theme = random.choice(themes)

    print(f"Seleccionado tema: {theme}")

    try:
        # Usar el método 'hashtag' para obtener videos relacionados con el hashtag
        hashtag_data = api.hashtag(name=theme.lstrip('#'))
        videos = []
        async for video in hashtag_data.videos(count=10):  # Consumir el generador asíncrono
            videos.append(video)

        if not videos:
            print(f"No se encontraron videos para el tema: {theme}")
            return

        video = random.choice(videos)
        video_url = f"https://www.tiktok.com/@{video.author.username}/video/{video.id}"
        print(f"Video seleccionado: {video_url}")

        channel = bot.get_channel(channel_id)
        if channel is None:
            print("Error: No se pudo encontrar el canal. Verifica el ID del canal.")
            return

        permissions = channel.permissions_for(channel.guild.me)
        if not permissions.send_messages:
            print("Error: El bot no tiene permisos para enviar mensajes en este canal.")
            return
        if not permissions.embed_links:
            print("Advertencia: El bot no tiene permisos para incluir enlaces embebidos.")
            
        # Descargar el video para adjuntarlo
        video_file = await download_tiktok_video(video_url)
        
        if video_file:
            # Enviar el mensaje con el video adjunto
            await channel.send(
                content=f"Aquí tienes un video de {theme}: {video_url}",
                file=discord.File(video_file)
            )
            # Eliminar el archivo temporal después de enviarlo
            os.remove(video_file)
        else:
            # Si no se pudo descargar, solo enviar el enlace
            await channel.send(f"Aquí tienes un video de {theme}: {video_url}")

    except discord.Forbidden:
        print("Error: El bot no tiene los permisos necesarios para realizar esta acción.")
    except KeyError as e:
        print(f"Error al procesar datos del video: {e}")
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

    if not api:
        await interaction.response.send_message("Error: TikTokApi no está configurada correctamente.", ephemeral=True)
        return

    # IMPORTANTE: Responder inmediatamente para evitar el error "La aplicación no respondió"
    await interaction.response.defer(thinking=True)
    
    try:
        # Seleccionar un tema aleatorio
        theme = random.choice(themes)
        
        # Informar al usuario
        await interaction.followup.send(f"🔍 Buscando videos de **{theme}**... Por favor espera.")
        
        # Obtener videos (puede tardar)
        hashtag_data = api.hashtag(name=theme.lstrip('#'))
        videos = []
        async for video in hashtag_data.videos(count=10):
            videos.append(video)
            
        if not videos:
            await interaction.followup.send(f"⚠️ No se encontraron videos para el tema: **{theme}**")
            return

        # Seleccionar un video aleatorio
        video = random.choice(videos)
        video_url = f"https://www.tiktok.com/@{video.author.username}/video/{video.id}"
        
        # Informar que se está descargando
        download_msg = await interaction.followup.send(f"⬇️ Descargando video de **{theme}**... Por favor espera.")
        
        # Descargar el video
        video_file = await download_tiktok_video(video_url)
        
        if video_file:
            # Enviar el video como archivo
            await interaction.followup.send(
                content=f"🎬 ¡Listo! Aquí tienes un video de **{theme}**: {video_url}",
                file=discord.File(video_file)
            )
            # Eliminar el mensaje de "descargando"
            try:
                await download_msg.delete()
            except:
                pass
            # Eliminar el archivo temporal
            os.remove(video_file)
        else:
            # Si no se pudo descargar, enviar solo el enlace
            await interaction.followup.send(f"⚠️ No se pudo descargar el video. Aquí está el enlace: {video_url}")
            
    except Exception as e:
        # Manejar cualquier error de manera segura
        error_msg = str(e)
        await interaction.followup.send(f"❌ Error al obtener el video: {error_msg}")
        print(f"Error en /enviar_video: {error_msg}")

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