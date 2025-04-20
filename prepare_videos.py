import os
import sys
import requests
import zipfile
import io

# Función para descargar un video genérico de Internet
def download_generic_video():
    # Crear directorio para videos si no existe
    videos_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "videos")
    if not os.path.exists(videos_dir):
        os.makedirs(videos_dir)
    
    # Destino del video de respaldo
    fallback_path = os.path.join(videos_dir, "fallback_video.mp4")
    
    # Si ya existe, no descargamos de nuevo
    if os.path.exists(fallback_path):
        print(f"El video genérico ya existe en: {fallback_path}")
        return
    
    # URL de un video genérico de Creative Commons
    urls = [
        "https://samplelib.com/lib/preview/mp4/sample-5s.mp4",
        "https://filesamples.com/samples/video/mp4/sample_640x360.mp4"
    ]
    
    for url in urls:
        try:
            print(f"Intentando descargar video de respaldo desde: {url}")
            response = requests.get(url, stream=True, timeout=30)
            if response.status_code == 200:
                # Guardar el archivo
                with open(fallback_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                print(f"Video genérico descargado a: {fallback_path}")
                return
        except Exception as e:
            print(f"Error al descargar desde {url}: {e}")
    
    print("No se pudo descargar ningún video genérico. Necesitarás proporcionar uno manualmente.")
    print(f"Coloca un video MP4 en: {fallback_path}")

if __name__ == "__main__":
    download_generic_video()
    print("Preparación de videos de respaldo completada.")
