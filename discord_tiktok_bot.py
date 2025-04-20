import discord
from discord.ext import commands, tasks
from TikTokApi import TikTokApi
import random
import os
from dotenv import load_dotenv
import json  # Importar módulo para manejar JSON
import threading  # Importar para manejar el acceso seguro a variables globales
from discord.ext.commands import cooldown, BucketType
import time

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
    import asyncio
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

# Lock para manejar el acceso seguro a la variable global themes
themes_lock = threading.Lock()

# Diccionario para almacenar los últimos mensajes enviados y prevenir duplicados
last_messages = {}

# Función auxiliar para evitar mensajes duplicados
async def send_unique_message(ctx, content):
    # Generar una clave única para el canal y el contenido
    message_key = f"{ctx.channel.id}:{content}"
    current_time = time.time()
    
    # Verificar si ya se envió un mensaje idéntico recientemente (en los últimos 3 segundos)
    if message_key in last_messages and current_time - last_messages[message_key] < 3:
        print(f"Se evitó enviar un mensaje duplicado: {content[:50]}...")
        return
    
    # Registrar el mensaje y enviarlo
    last_messages[message_key] = current_time
    await ctx.send(content)
    
    # Limpieza de mensajes antiguos (más de 30 segundos)
    for key in list(last_messages.keys()):
        if current_time - last_messages[key] > 30:
            del last_messages[key]

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
    try:
        with themes_lock:  # Asegurar acceso seguro a la variable global
            themes_copy = themes[:]  # Crear una copia de la lista para evitar conflictos
        with open(themes_file, "w", encoding="utf-8") as f:
            json.dump(themes_copy, f, ensure_ascii=False, indent=4)
            print("Temas guardados correctamente.")
    except Exception as e:
        print(f"Error al guardar los temas en el archivo: {e}")

# Lista para almacenar los temas asignados
themes = []

# Cargar los temas al iniciar el bot
load_themes()

# Comando para asignar temas (hashtags) con cooldown
@bot.command(name='asignar_tema')
@cooldown(1, 3, BucketType.user)  # 1 uso cada 3 segundos por usuario
async def assign_theme(ctx, *args):
    global themes
    new_themes = list(set(filter(None, args)))  # Filtrar temas vacíos
    if not new_themes:
        await send_unique_message(ctx, "Por favor, proporciona al menos un tema válido. Los temas vacíos no son permitidos.")
        return

    with themes_lock:
        already_added = [theme for theme in new_themes if theme in themes]
        new_to_add = [theme for theme in new_themes if theme not in themes]

        # Solo un mensaje de respuesta, según el caso
        if already_added and not new_to_add:
            await send_unique_message(ctx, f"Los siguientes temas ya están agregados: {', '.join(already_added)}.\nTemas actuales: {', '.join(themes)}")
        elif new_to_add and not already_added:
            themes.extend(new_to_add)
            save_themes()
            await send_unique_message(ctx, f"Nuevos temas agregados: {', '.join(new_to_add)}.\nTemas actuales: {', '.join(themes)}")
        elif new_to_add and already_added:
            themes.extend(new_to_add)
            save_themes()
            await send_unique_message(ctx, 
                f"Los siguientes temas ya estaban agregados: {', '.join(already_added)}.\n"
                f"Nuevos temas agregados: {', '.join(new_to_add)}.\n"
                f"Temas actuales: {', '.join(themes)}"
            )

# Comando para eliminar un tema (hashtag) con cooldown
@bot.command(name='eliminar_tema')
@cooldown(1, 3, BucketType.user)  # 1 uso cada 3 segundos por usuario
async def remove_theme(ctx, theme: str):
    global themes
    with themes_lock:  # Asegurar acceso seguro a la variable global
        if theme in themes:
            themes.remove(theme)
            save_themes()  # Guardar los temas actualizados
            await send_unique_message(ctx, f'Tema eliminado: {theme}')
        else:
            await send_unique_message(ctx, f'El tema "{theme}" no se encuentra en la lista.')

# Comando para ver todos los temas asignados con cooldown
@bot.command(name='ver_temas')
@cooldown(1, 3, BucketType.user)  # 1 uso cada 3 segundos por usuario
async def view_themes(ctx):
    global themes
    with themes_lock:  # Asegurar acceso seguro a la variable global
        if themes:
            await send_unique_message(ctx, f'Temas asignados: {", ".join(themes)}')
        else:
            await send_unique_message(ctx, "No hay temas asignados actualmente.")

# Comando de ayuda con cooldown
@bot.command(name='ayuda')
@cooldown(1, 5, BucketType.user)  # 1 uso cada 5 segundos por usuario
async def help_command(ctx):
    help_message = """
**Lista de comandos disponibles:**

1. **_asignar_tema [temas...]**
   - Descripción: Asigna uno o más temas (hashtags) para buscar videos de TikTok.
   - Ejemplo: `_asignar_tema #meme #funny`

2. **_eliminar_tema [tema]**
   - Descripción: Elimina un tema (hashtag) de la lista de temas asignados.
   - Ejemplo: `_eliminar_tema #meme`

3. **_ver_temas**
   - Descripción: Muestra todos los temas (hashtags) actualmente asignados.
   - Ejemplo: `_ver_temas`

4. **/enviar_video**
   - Descripción: Envía un video aleatorio de TikTok basado en los temas asignados.
   - Nota: Este es un comando de aplicación (slash command).

5. **_ayuda**
   - Descripción: Muestra esta lista de ayuda con información sobre los comandos disponibles.
   - Ejemplo: `_ayuda`

**Notas adicionales:**
- Los temas asignados se guardan de manera persistente y no se pierden al reiniciar el bot.
- Asegúrate de que el bot tenga permisos para enviar mensajes y enlaces en el canal correspondiente.
"""
    await send_unique_message(ctx, help_message)

# Tarea periódica para enviar videos aleatorios
@tasks.loop(hours=1)
async def send_random_video():
    global themes
    if not api:
        print("Error: TikTokApi no está configurada correctamente. La tarea no se ejecutará.")
        return

    with themes_lock:  # Asegurar acceso seguro a la variable global
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
    if not themes:
        await interaction.response.send_message("No hay temas asignados. Usa `_asignar_tema` para añadir algunos.", ephemeral=True)
        return

    if not api:
        await interaction.response.send_message("Error: TikTokApi no está configurada correctamente.", ephemeral=True)
        return

    theme = random.choice(themes)
    try:
        videos = api.by_hashtag(theme.lstrip('#'), count=10)
        if not videos:
            await interaction.response.send_message(f"No se encontraron videos para el tema: {theme}", ephemeral=True)
            return

        video = random.choice(videos)
        video_url = f"https://www.tiktok.com/@{video['author']['uniqueId']}/video/{video['id']}"

        permissions = interaction.channel.permissions_for(interaction.guild.me)
        if not permissions.send_messages:
            await interaction.response.send_message("Error: El bot no tiene permisos para enviar mensajes en este canal.", ephemeral=True)
            return
        if not permissions.embed_links:
            await interaction.response.send_message("Advertencia: El bot no tiene permisos para incluir enlaces embebidos.", ephemeral=True)

        await interaction.response.send_message(f"Aquí tienes un video de {theme}: {video_url}")
    except discord.Forbidden:
        await interaction.response.send_message("Error: El bot no tiene permisos para enviar mensajes en este canal.", ephemeral=True)
    except KeyError as e:
        await interaction.response.send_message(f"Error al procesar datos del video: {str(e)}", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Error al obtener el video: {str(e)}", ephemeral=True)

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
    except Exception as e:
        print(f"Error al iniciar la tarea periódica: {e}")

# Evento para manejar errores de cooldown
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        remaining = round(error.retry_after, 1)
        await ctx.send(f"Por favor espera {remaining}s antes de usar este comando nuevamente.", delete_after=5)
    else:
        print(f"Error no manejado: {error}")

# Cargar el token desde el archivo .env
token = os.getenv('BOT_TOKEN')

if not token:
    raise ValueError("El token del bot no se ha encontrado. Asegúrate de que el archivo .env contiene 'BOT_TOKEN'.")

if len(token) < 50:
    raise ValueError("El token parece inválido. Verifica que sea correcto.")

bot.run(token)