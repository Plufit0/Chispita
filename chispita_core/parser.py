import re
from .utils import unescape_special_sequences

def parsear_supertexto(contenido_texto):
    """
    Parsea el supertexto y retorna una lista de comandos estructurados.
    MODO ESTRICTO v1.2 (Python 3.14 Compatible):
    - Elimina flags inline (?m) que causan crash en Python nuevos.
    - Usa flags explícitos en la llamada a re.finditer.
    """
    
    TAG_END = "<<<" + "END>>>"
    TAG_OLD = "<<<" + "OLD>>>"
    TAG_NEW = "<<<" + "NEW>>>"

    # Regex Principal
    # Explicación:
    # ^---(\w+)   -> Busca inicio de línea (gracias a re.MULTILINE), luego ---COMANDO
    # (?:...)     -> Grupo no captura para la ruta opcional
    # \s*[\r\n]+  -> Consume espacios y el salto de línea obligatorio
    # (.*?)       -> Captura todo el contenido (non-greedy)
    # ^TAG_END    -> Hasta encontrar el tag de cierre al inicio de una línea
    patron_comando = r'^---(\w+)(?::(.+?))?---\s*[\r\n]+(.*?)^' + re.escape(TAG_END)
    
    # FIX CRÍTICO PYTHON 3.14: Pasamos los flags aquí, no dentro del string
    matches = re.finditer(patron_comando, contenido_texto, re.MULTILINE | re.DOTALL)
    
    comandos = []
    for match in matches:
        comando = match.group(1)
        ruta = match.group(2).strip() if match.group(2) else None
        raw_content = match.group(3) if match.group(3) else ""
        
        # Limpieza quirúrgica de saltos de línea finales
        if raw_content.endswith('\r\n'):
            contenido_completo = raw_content[:-2]
        elif raw_content.endswith('\n'):
            contenido_completo = raw_content[:-1]
        else:
            contenido_completo = raw_content

        if comando == 'REPLACE_BLOCK':
            # FIX CRÍTICO: También corregimos el regex interno de REPLACE_BLOCK
            patron_replace = r'^' + re.escape(TAG_OLD) + r'[\r\n]+(.*?)^' + re.escape(TAG_NEW)
            
            old_match = re.search(patron_replace, contenido_completo, re.MULTILINE | re.DOTALL)
            
            if old_match:
                old_raw = old_match.group(1)
                # Limpieza quirúrgica OLD
                if old_raw.endswith('\r\n'): old_content = old_raw[:-2]
                elif old_raw.endswith('\n'): old_content = old_raw[:-1]
                else: old_content = old_raw
                
                new_start = old_match.end()
                new_raw = contenido_completo[new_start:]
                
                # Limpieza quirúrgica NEW
                if new_raw.startswith('\r\n'): new_content = new_raw[2:]
                elif new_raw.startswith('\n'): new_content = new_raw[1:]
                else: new_content = new_raw
                
                comandos.append({
                    'comando': comando,
                    'ruta': ruta,
                    'contenido_old': unescape_special_sequences(old_content),
                    'contenido_new': unescape_special_sequences(new_content)
                })
            else:
                print(f"[WARN] REPLACE_BLOCK mal formado en {ruta}. Faltan etiquetas OLD/NEW.")
        
        elif comando == 'CREAR':
            comandos.append({
                'comando': comando,
                'ruta': ruta,
                'contenido': unescape_special_sequences(contenido_completo)
            })
        
        else:
            # Comandos sin contenido (ELIMINAR, EXPORT_*, GIT_COMMIT)
            comandos.append({'comando': comando, 'ruta': ruta, 'contenido': None})
    
    return comandos