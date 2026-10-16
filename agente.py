import csv
import json
import os
import sys
import unicodedata
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from google import genai

MODELO = "gemini-3.5-flash-lite"
RUTA_INSTRUCCIONES = Path(__file__).parent / "prompts" / "sistema.md"
RUTA_CONOCIMIENTO = Path(__file__).parent / "conocimiento"
RUTA_GASTOS = RUTA_CONOCIMIENTO / "gastos.csv"
RUTA_SOLICITUDES = Path(__file__).parent / "solicitudes.csv"
MAX_VUELTAS = 5

HERRAMIENTAS = [
    {
        "type": "function",
        "name": "sumar_gastos",
        "description": (
            "Cuenta y suma los gastos de viaje registrados en gastos.csv. Úsala siempre que "
            "pregunten cuánto suman, cuánto se gastó o cuántos gastos hay, en total o por área "
            "y/o estado. No sirve para consultar topes ni reglas de la política."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "area": {
                    "type": "string",
                    "description": "Área de la empresa, por ejemplo Ventas u Operaciones. Omítela para incluir todas.",
                },
                "estado": {
                    "type": "string",
                    "description": "Estado del gasto: Aprobado, Pendiente o Rechazado. Omítelo para incluir todos.",
                },
            },
        },
    },
    {
        "type": "function",
        "name": "registrar_solicitud",
        "description": (
            "Registra una nueva solicitud de viáticos y devuelve su radicado. Úsala solo cuando "
            "el usuario pida registrar una solicitud y haya dado los cinco datos: empleado, "
            "ciudad, fecha de salida, número de noches y motivo. Si falta alguno, no la llames."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "empleado": {"type": "string", "description": "Nombre completo del empleado que viaja."},
                "ciudad": {"type": "string", "description": "Ciudad de destino."},
                "fecha_salida": {"type": "string", "description": "Fecha de salida en formato AAAA-MM-DD."},
                "noches": {"type": "integer", "description": "Número de noches del viaje."},
                "motivo": {"type": "string", "description": "Motivo del viaje."},
            },
            "required": ["empleado", "ciudad", "fecha_salida", "noches", "motivo"],
        },
    },
]


def normalizar(texto):
    """Pasa a minúsculas y quita las tildes para comparar sin importar cómo se escriba."""
    sin_tildes = unicodedata.normalize("NFD", texto)
    sin_tildes = "".join(letra for letra in sin_tildes if unicodedata.category(letra) != "Mn")
    return sin_tildes.strip().lower()


def sumar_gastos(area=None, estado=None):
    """Cuenta y suma los gastos de gastos.csv, filtrando opcionalmente por área y estado."""
    filas = 0
    total = 0
    with RUTA_GASTOS.open(encoding="utf-8", newline="") as archivo:
        for gasto in csv.DictReader(archivo):
            if area and normalizar(gasto["area"]) != normalizar(area):
                continue
            if estado and normalizar(gasto["estado"]) != normalizar(estado):
                continue
            filas += 1
            total += int(gasto["valor_cop"])
    return {"filas": filas, "total_cop": total}


def registrar_solicitud(empleado, ciudad, fecha_salida, noches, motivo):
    """Agrega una solicitud a solicitudes.csv con un radicado consecutivo y devuelve el radicado."""
    columnas = ["radicado", "fecha_registro", "empleado", "ciudad", "fecha_salida", "noches", "motivo", "estado"]
    existentes = 0
    if RUTA_SOLICITUDES.exists():
        with RUTA_SOLICITUDES.open(encoding="utf-8", newline="") as archivo:
            existentes = sum(1 for _ in csv.DictReader(archivo))
    radicado = f"S-{existentes + 1:03d}"
    nuevo = not RUTA_SOLICITUDES.exists()
    with RUTA_SOLICITUDES.open("a", encoding="utf-8", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=columnas)
        if nuevo:
            escritor.writeheader()
        escritor.writerow({
            "radicado": radicado,
            "fecha_registro": date.today().isoformat(),
            "empleado": empleado,
            "ciudad": ciudad,
            "fecha_salida": fecha_salida,
            "noches": int(noches),
            "motivo": motivo,
            "estado": "Pendiente de aprobación del jefe inmediato",
        })
    return {"radicado": radicado}


FUNCIONES = {"sumar_gastos": sumar_gastos, "registrar_solicitud": registrar_solicitud}


def ejecutar_herramienta(llamada):
    """Ejecuta la función que pidió el modelo, imprime la traza y devuelve el resultado."""
    try:
        resultado = FUNCIONES[llamada.name](**llamada.arguments)
    except Exception as error:
        resultado = {"error": str(error)}
    print(f"[herramienta] {llamada.name} | argumentos: {llamada.arguments} | resultado: {resultado}")
    return resultado


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
    """Lee los archivos .md de conocimiento/ y los devuelve envueltos en etiquetas <documento>.

    gastos.csv no se agrega: los gastos se consultan con la herramienta sumar_gastos.
    """
    if not RUTA_CONOCIMIENTO.is_dir():
        sys.exit(f"No se encontró la carpeta de conocimiento: {RUTA_CONOCIMIENTO}")
    archivos = sorted(ruta for ruta in RUTA_CONOCIMIENTO.iterdir() if ruta.is_file() and ruta.suffix == ".md")
    if not archivos:
        sys.exit(f"La carpeta de conocimiento está vacía: {RUTA_CONOCIMIENTO}")
    documentos = []
    for ruta in archivos:
        contenido = ruta.read_text(encoding="utf-8").strip()
        documentos.append(f'<documento nombre="{ruta.name}">\n{contenido}\n</documento>')
    return "\n\n".join(documentos)


def preguntar(cliente, pregunta, instrucciones, interaccion_previa=None):
    """Envía la pregunta, ejecuta las herramientas que pida el modelo y devuelve (respuesta, id de la interacción)."""
    entrada = pregunta
    for _ in range(MAX_VUELTAS):
        parametros = {
            "model": MODELO,
            "input": entrada,
            "system_instruction": instrucciones,
            "tools": HERRAMIENTAS,
        }
        # El id de la interacción anterior le da al modelo la memoria de la conversación.
        if interaccion_previa:
            parametros["previous_interaction_id"] = interaccion_previa
        interaccion = cliente.interactions.create(**parametros)
        interaccion_previa = interaccion.id

        llamadas = [paso for paso in interaccion.steps if paso.type == "function_call"]
        if not llamadas:
            return interaccion.output_text, interaccion.id

        # El modelo pidió herramientas: se ejecutan y en la siguiente vuelta se le envían los resultados.
        entrada = [
            {
                "type": "function_result",
                "name": llamada.name,
                "call_id": llamada.id,
                "result": [{"type": "text", "text": json.dumps(ejecutar_herramienta(llamada), ensure_ascii=False)}],
            }
            for llamada in llamadas
        ]
    return "No pude completar la respuesta después de varios intentos. Intenta de nuevo.", interaccion_previa


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
