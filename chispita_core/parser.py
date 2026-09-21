import re
from .utils import unescape_special_sequences

# ==========================================================================
#  MODIFICADORES CONOCIDOS (v2.0)
#  Se usan como whitelist para distinguir una línea "key: value" (modificador)
#  de una línea de datos (por ejemplo una ruta de Windows "C:/Users/...").
#  Esto es CRÍTICO: sin la whitelist, "C:/Users" se leería como el
#  modificador key="C", value="/Users..." y corrompería los BATCH_*.
# ==========================================================================
MODIFICADORES_CONOCIDOS = {
    # Filtrado
    'exclude', 'only', 'depth', 'include_hidden', 'follow_junctions',
    # Tamaño
    'min_size', 'max_size',
    # Fecha
    'older_than', 'newer_than', 'by',
    # Salida
    'format', 'sort', 'top', 'group_by', 'output_to',
    # Contenido / hashing
    'hash_algo', 'hash_sample',
    # Seguridad
    'dry_run', 'max_affected', 'confirm',
    # Renombrado
    'pattern', 'template',
}

# Comandos cuyo cuerpo es CONTENIDO LITERAL de archivo: no se parsean
# modificadores dentro de ellos (romperían el contenido).
COMANDOS_CON_CONTENIDO = {'CREAR', 'REPLACE_BLOCK'}


def _limpiar_saltos_finales(raw):
    """Elimina un único salto de línea final (\\r\\n o \\n)."""
    if raw.endswith('\r\n'):
        return raw[:-2]
    if raw.endswith('\n'):
        return raw[:-1]
    return raw


def separar_modificadores(cuerpo):
    """
    Separa el cuerpo de un comando declarativo en:
      - modificadores: dict {clave: valor} (solo claves en la whitelist)
      - lineas: lista de líneas que NO son modificadores (ej. rutas en BATCH_MOVE)
    Ignora líneas vacías al armar 'lineas'.
    """
    modificadores = {}
    lineas = []
    for linea in cuerpo.splitlines():
        stripped = linea.strip()
        if not stripped:
            continue
        m = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*(.*)$', stripped)
        if m and m.group(1) in MODIFICADORES_CONOCIDOS:
            modificadores[m.group(1)] = m.group(2).strip()
        else:
            lineas.append(stripped)
    return modificadores, lineas


def parsear_supertexto(contenido_texto):
    """
    Parsea el supertexto y retorna una lista de comandos estructurados.

    v2.0:
    - Soporta líneas secundarias "key: value" (modificadores) en comandos
      declarativos, sin tocar el contenido literal de CREAR/REPLACE_BLOCK.
    - Soporta el bloque global ---CONFIG--- para flags de toda la corrida
      (dry_run, format, max_affected, confirm, output_to).
    - Comandos nuevos (EXPORT_INVENTORY/DUPLICATES/SIZES, BATCH_MOVE,
      BATCH_RENAME, TRASH) llegan con sus modificadores y líneas de datos.

    MODO ESTRICTO (Python 3.14 Compatible):
    - Sin flags inline (?m); flags explícitos en re.finditer.
    """

    TAG_END = "<<<" + "END>>>"
    TAG_OLD = "<<<" + "OLD>>>"
    TAG_NEW = "<<<" + "NEW>>>"

    patron_comando = r'^---(\w+)(?::(.+?))?---\s*[\r\n]+(.*?)^' + re.escape(TAG_END)
    matches = re.finditer(patron_comando, contenido_texto, re.MULTILINE | re.DOTALL)

    comandos = []
    for match in matches:
        comando = match.group(1)
        ruta = match.group(2).strip() if match.group(2) else None
        raw_content = match.group(3) if match.group(3) else ""
        contenido_completo = _limpiar_saltos_finales(raw_content)

        if comando == 'REPLACE_BLOCK':
            patron_replace = r'^' + re.escape(TAG_OLD) + r'[\r\n]+(.*?)^' + re.escape(TAG_NEW)
            old_match = re.search(patron_replace, contenido_completo, re.MULTILINE | re.DOTALL)

            if old_match:
                old_content = _limpiar_saltos_finales(old_match.group(1))
                new_raw = contenido_completo[old_match.end():]
                if new_raw.startswith('\r\n'):
                    new_content = new_raw[2:]
                elif new_raw.startswith('\n'):
                    new_content = new_raw[1:]
                else:
                    new_content = new_raw

                comandos.append({
                    'comando': comando,
                    'ruta': ruta,
                    'contenido_old': unescape_special_sequences(old_content),
                    'contenido_new': unescape_special_sequences(new_content),
                    'modificadores': {},
                    'lineas': [],
                })
            else:
                print(f"[WARN] REPLACE_BLOCK mal formado en {ruta}. Faltan etiquetas OLD/NEW.")

        elif comando == 'CREAR':
            comandos.append({
                'comando': comando,
                'ruta': ruta,
                'contenido': unescape_special_sequences(contenido_completo),
                'modificadores': {},
                'lineas': [],
            })

        else:
            # Comandos declarativos: el cuerpo son modificadores y/o líneas de datos.
            modificadores, lineas = separar_modificadores(contenido_completo)
            comandos.append({
                'comando': comando,
                'ruta': ruta,
                'contenido': None,
                'modificadores': modificadores,
                'lineas': lineas,
            })

    return comandos
