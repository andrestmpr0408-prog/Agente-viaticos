import os
import sys

from dotenv import load_dotenv
from google import genai

MODELO = "gemini-3.5-flash-lite"
INSTRUCCIONES = "Eres un asistente útil. Responde en español, como un cavernicola."


def crear_cliente():
    load_dotenv()
    llave = os.getenv("GEMINI_API_KEY")
    if not llave or llave == "pega_aqui_tu_llave":
        sys.exit("Falta GEMINI_API_KEY. Copia .env.example como .env y pega tu llave.")
    return genai.Client(api_key=llave)


def preguntar(cliente, pregunta, interaccion_previa=None):
    """Envía la pregunta y devuelve (respuesta, id de la interacción)."""
    parametros = {
        "model": MODELO,
        "input": pregunta,
        "system_instruction": INSTRUCCIONES,
    }
    # El id de la interacción anterior le da al modelo la memoria de la conversación.
    if interaccion_previa:
        parametros["previous_interaction_id"] = interaccion_previa
    interaccion = cliente.interactions.create(**parametros)
    return interaccion.output_text, interaccion.id


def main():
    cliente = crear_cliente()

    # Uso directo: python agente.py "¿Cuál es la capital de Colombia?"
    if len(sys.argv) > 1:
        try:
            respuesta, _ = preguntar(cliente, " ".join(sys.argv[1:]))
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
            respuesta, interaccion_previa = preguntar(cliente, pregunta, interaccion_previa)
        except Exception as error:
            print(f"Error al consultar el modelo: {error}")
            continue
        print(f"\nAgente: {respuesta}")


if __name__ == "__main__":
    main()
