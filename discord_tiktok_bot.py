import discord
from discord.ext import commands, tasks
from discord import app_commands
from TikTokApi import TikTokApi
import random
import asyncio
import os
from dotenv import load_dotenv
import json  # Importar módulo para manejar JSON

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
    api = TikTokApi.get_instance(use_test_endpoints=True)
except Exception as e:
    print(f"Error al inicializar TikTokApi: {e}")
    api = None

# Ruta del archivo para almacenar los temas
themes_file = "themes.json"

# Función para cargar los temas desde el archivo
def load_themes():
    global themes
    if os.path.exists(themes_file):
        try:
            with open(themes_file, "r", encoding="utf-8") as f:
                themes = json.load(f)
                print(f"Temas cargados: {themes}")
        except Exception as e:
            print(f"Error al cargar los temas desde el archivo: {e}")
            themes = []
    else:
        themes = []

# Función para guardar los temas en el archivo
def save_themes():
    try:
        with open(themes_file, "w", encoding="utf-8") as f:
            json.dump(themes, f, ensure_ascii=False, indent=4)
            print("Temas guardados correctamente.")
    except Exception as e:
        print(f"Error al guardar los temas en el archivo: {e}")

# Lista para almacenar los temas asignados
themes = []

# Cargar los temas al iniciar el bot
load_themes()

# Comando para asignar temas (hashtags)
@bot.command(name='asignar_tema')
async def assign_theme(ctx, *args):
    global themes
    new_themes = list(set(filter(None, args)))  # Filtrar temas vacíos
    if not new_themes:
        await ctx.send("No se pueden agregar temas vacíos. Por favor, proporciona al menos un tema válido.")
        return

    already_added = [theme for theme in new_themes if theme in themes]
    new_to_add = [theme for theme in new_themes if theme not in themes]

    if already_added:
        await ctx.send(f"Los siguientes temas ya están agregados: {', '.join(already_added)}")
    if new_to_add:
        themes.extend(new_to_add)
        save_themes()  # Guardar los temas actualizados
        await ctx.send(f"Nuevos temas agregados: {', '.join(new_to_add)}")
    await ctx.send(f'Temas actuales: {", ".join(themes)}')

# Comando para eliminar un tema (hashtag)
@bot.command(name='eliminar_tema')
async def remove_theme(ctx, theme: str):
    global themes
    if theme in themes:
        themes.remove(theme)
        save_themes()  # Guardar los temas actualizados
        await ctx.send(f'Tema eliminado: {theme}')
    else:
        await ctx.send(f'El tema "{theme}" no se encuentra en la lista.')

# Comando para ver todos los temas asignados
@bot.command(name='ver_temas')
async def view_themes(ctx):
    global themes
    if themes:
        await ctx.send(f'Temas asignados: {", ".join(themes)}')
    else:
        await ctx.send("No hay temas asignados actualmente.")

# Tarea periódica para enviar videos aleatorios
@tasks.loop(hours=1)
async def send_random_video():
    if not themes:
        print("No hay temas asignados. La tarea no se ejecutará.")
        return

    theme = random.choice(themes)
    print(f"Seleccionado tema: {theme}")

    try:
        if not api:
            print("Error: TikTokApi no está configurada correctamente.")
            return

        videos = api.by_hashtag(theme.lstrip('#'), count=10)
        if not videos:
            print(f"No se encontraron videos para el tema: {theme}")
            return

        video = random.choice(videos)
        video_url = f"https://www.tiktok.com/@{video['author']['uniqueId']}/video/{video['id']}"
        print(f"Video seleccionado: {video_url}")

        channel = bot.get_channel(1363398384890941611)
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
    if not themes:
        await interaction.response.send_message("No hay temas asignados. Usa `_asignar_tema` para añadir algunos.", ephemeral=True)
        return

    theme = random.choice(themes)
    try:
        if not api:
            await interaction.response.send_message("Error: TikTokApi no está configurada correctamente.", ephemeral=True)
            return

        videos = api.by_hashtag(theme.lstrip('#'), count=10)
        if not videos:
            await interaction.response.send_message(f"No se encontraron videos para el tema: {theme}", ephemeral=True)
            return

        video = random.choice(videos)
        video_url = f"https://www.tiktok.com/@{video['author']['uniqueId']}/video/{video['id']}"

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
        channel = bot.get_channel(1363398384890941611)
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

# Cargar el token desde el archivo .env
token = os.getenv('BOT_TOKEN')

if not token:
    raise ValueError("El token del bot no se ha encontrado. Asegúrate de que el archivo .env contiene 'BOT_TOKEN'.")

if len(token) < 50:
    raise ValueError("El token parece inválido. Verifica que sea correcto.")

bot.run(token)