import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai

MODELO = "gemini-3.5-flash-lite"
RUTA_INSTRUCCIONES = Path(__file__).parent / "prompts" / "sistema.md"
RUTA_CONOCIMIENTO = Path(__file__).parent / "conocimiento"


def crear_cliente():
    load_dotenv()
    llave = os.getenv("GEMINI_API_KEY")
    if not llave or llave == "pega_aqui_tu_llave":
        sys.exit("Falta GEMINI_API_KEY. Copia .env.example como .env y pega tu llave.")
    return genai.Client(api_key=llave)


def cargar_instrucciones():
    try:
        instrucciones = RUTA_INSTRUCCIONES.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        sys.exit(f"No se encontró el archivo de instrucciones: {RUTA_INSTRUCCIONES}")
    if not instrucciones:
        sys.exit(f"El archivo de instrucciones está vacío: {RUTA_INSTRUCCIONES}")
    return instrucciones + "\n\n" + cargar_conocimiento()


def cargar_conocimiento():
    """Lee todos los archivos de conocimiento/ y los devuelve envueltos en etiquetas <documento>."""
    if not RUTA_CONOCIMIENTO.is_dir():
        sys.exit(f"No se encontró la carpeta de conocimiento: {RUTA_CONOCIMIENTO}")
    archivos = sorted(ruta for ruta in RUTA_CONOCIMIENTO.iterdir() if ruta.is_file())
    if not archivos:
        sys.exit(f"La carpeta de conocimiento está vacía: {RUTA_CONOCIMIENTO}")
    documentos = []
    for ruta in archivos:
        contenido = ruta.read_text(encoding="utf-8").strip()
        documentos.append(f'<documento nombre="{ruta.name}">\n{contenido}\n</documento>')
    return "\n\n".join(documentos)


def preguntar(cliente, pregunta, instrucciones, interaccion_previa=None):
    """Envía la pregunta y devuelve (respuesta, id de la interacción)."""
    parametros = {
        "model": MODELO,
        "input": pregunta,
        "system_instruction": instrucciones,
    }
    # El id de la interacción anterior le da al modelo la memoria de la conversación.
    if interaccion_previa:
        parametros["previous_interaction_id"] = interaccion_previa
    interaccion = cliente.interactions.create(**parametros)
    return interaccion.output_text, interaccion.id


def main():
    cliente = crear_cliente()
    instrucciones = cargar_instrucciones()

    # Uso directo: python agente.py "¿Cuál es la capital de Colombia?"
    if len(sys.argv) > 1:
        try:
            respuesta, _ = preguntar(cliente, " ".join(sys.argv[1:]), instrucciones)
        except Exception as error:
            sys.exit(f"Error al consultar el modelo: {error}")
        print(respuesta)
        return

    print("Agente listo. Escribe tu pregunta (o 'salir' para terminar).")
    interaccion_previa = None
    while True:
        try:
            pregunta = input("\nTú: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not pregunta:
            continue
        if pregunta.lower() in ("salir", "exit", "quit"):
            break
        try:
            respuesta, interaccion_previa = preguntar(cliente, pregunta, instrucciones, interaccion_previa)
        except Exception as error:
            print(f"Error al consultar el modelo: {error}")
            continue
        print(f"\nAgente: {respuesta}")


if __name__ == "__main__":
    main()
