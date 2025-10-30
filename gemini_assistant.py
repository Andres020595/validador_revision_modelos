import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

def cargar_modelo():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("❌ No se encontró GOOGLE_API_KEY en el archivo .env")

    genai.configure(api_key=api_key)
    modelo = genai.GenerativeModel("gemini-1.5-pro-latest")
    return modelo

def sugerir_epsg(ubicacion):
    modelo = cargar_modelo()
    prompt = f"""
    Estás actuando como un asistente GIS. Un usuario ha escrito la siguiente descripción sobre la ubicación de su proyecto:

    '{ubicacion}'

    Con base en esto, devuelve únicamente el código EPSG más apropiado para esa zona geográfica. No expliques nada, solo responde con un valor como: EPSG:25830
    """
    respuesta = modelo.generate_content(prompt)
    return respuesta.text.strip()