import os
import subprocess
import shutil

# Configuración de extensiones válidas para exportar
EXTENSIONES_VALIDAS = [
    '.py', '.js', '.ts', '.gd', '.c', '.cpp', '.h', '.hpp', '.java', '.rs', '.go',
    '.json', '.xml', '.yaml', '.yml', '.toml', '.cfg', '.ini', '.env',
    '.html', '.css', '.md', '.txt', '.rst',
    '.tscn', '.tres', '.godot', '.import',
    '.csv', '.sql', '.graphql', '.shader',
    '.bat', '.sh', '.cmd'
]
ARCHIVOS_ESPECIALES = ['project.godot', 'Makefile', 'Dockerfile', '.gitignore', 'requirements.txt']

def limpiar_ruta(ruta):
    """Normaliza rutas de Godot (res://) a rutas de sistema."""
    if not ruta: return "."
    return ruta.replace("res://", "").replace("\\", "/")

def crear_archivo(ruta, contenido):
    from chispita_core.i18n import translator
    try:
        ruta_limpia = limpiar_ruta(ruta)
        directorio = os.path.dirname(ruta_limpia)
        if directorio:
            os.makedirs(directorio, exist_ok=True)
        
        with open(ruta_limpia, 'w', encoding='utf-8', newline='\n') as f:
            f.write(contenido)
        return True
    except Exception as e:
        print(f"{translator.get('io_err_create')} {ruta}: {e}")
        return False

def eliminar_archivo(ruta):
    from chispita_core.i18n import translator
    try:
        ruta_limpia = limpiar_ruta(ruta)
        if not os.path.exists(ruta_limpia):
            print(f"{translator.get('io_warn_del_no_exist')} {ruta_limpia}")
            return False
        
        if os.path.isfile(ruta_limpia):
            os.remove(ruta_limpia)
        elif os.path.isdir(ruta_limpia):
            shutil.rmtree(ruta_limpia)
            
        return True
    except Exception as e:
        print(f"{translator.get('io_err_del')} {ruta}: {e}")
        return False

def replace_block(ruta, contenido_old, contenido_new):
    from chispita_core.i18n import translator
    try:
        ruta_limpia = limpiar_ruta(ruta)
        if not os.path.exists(ruta_limpia):
            print(f"{translator.get('io_err_replace_no_exist')} {ruta_limpia}")
            return False
        
        with open(ruta_limpia, 'r', encoding='utf-8') as f:
            contenido_original = f.read()
        
        if contenido_old not in contenido_original:
            print(f"{translator.get('io_warn_old_not_found')} {ruta_limpia}.")
            print(translator.get('io_diag_attempt'))
            print(f"{translator.get('io_diag_searched')} (len={len(contenido_old)}):\n{contenido_old[:100]}...")
            print("------------------------------")
            return False
        
        contenido_modificado = contenido_original.replace(contenido_old, contenido_new, 1)
        
        with open(ruta_limpia, 'w', encoding='utf-8', newline='\n') as f:
            f.write(contenido_modificado)
        return True
    except Exception as e:
        print(f"{translator.get('io_err_replace')} {e}")
        return False

def leer_archivo_seguro(ruta):
    """Intenta leer un archivo manejando errores de encoding."""
    try:
        with open(ruta, 'r', encoding='utf-8') as f:
            return f.read()
    except UnicodeDecodeError:
        return "[OMITIDO: Archivo binario o codificación no soportada]"
    except Exception as e:
        return f"[ERROR LEER: {e}]"

def export_file(ruta_archivo):
    from chispita_core.i18n import translator
    ruta_limpia = limpiar_ruta(ruta_archivo)
    if not os.path.exists(ruta_limpia):
        return f"{translator.get('io_err_export_no_exist')} '{ruta_limpia}'"
    
    contenido = leer_archivo_seguro(ruta_limpia)
    return f"--- FILE: {ruta_limpia} ---\n{contenido}"

def generar_arbol(ruta_base, solo_carpetas=False):
    """Genera una representación en texto del árbol de directorios estilo 'tree'."""
    ruta_limpia = limpiar_ruta(ruta_base)
    if not os.path.exists(ruta_limpia):
        return f"[ERROR] Árbol: '{ruta_limpia}' no existe."
        
    IGNORAR_CARPETAS = {'.git', '.godot', '__pycache__', 'venv', 'node_modules', 'exports'}
    
    lineas = [f"Directorio: {os.path.abspath(ruta_limpia)}"]
    
    def construir_rama(ruta_actual, prefijo=""):
        try:
            entradas = os.listdir(ruta_actual)
        except PermissionError:
            return
            
        directorios = []
        archivos = []
        
        for e in entradas:
            ruta_e = os.path.join(ruta_actual, e)
            if os.path.isdir(ruta_e):
                if e not in IGNORAR_CARPETAS:
                    directorios.append(e)
            else:
                if not solo_carpetas:
                    archivos.append(e)
                    
        directorios.sort()
        archivos.sort()
        elementos = directorios + archivos
        total_elementos = len(elementos)
        
        for i, nombre in enumerate(elementos):
            es_ultimo = (i == total_elementos - 1)
            conector = "└── " if es_ultimo else "├── "
            nuevo_prefijo = prefijo + ("    " if es_ultimo else "│   ")
            
            es_directorio = nombre in directorios
            if es_directorio:
                lineas.append(f"{prefijo}{conector}[DIR] {nombre}")
                construir_rama(os.path.join(ruta_actual, nombre), nuevo_prefijo)
            else:
                lineas.append(f"{prefijo}{conector}{nombre}")
                
    construir_rama(ruta_limpia)
    return "\n".join(lineas)

def export_folder(ruta_carpeta):
    from chispita_core.i18n import translator
    ruta_limpia = limpiar_ruta(ruta_carpeta)
    if not os.path.exists(ruta_limpia):
        return f"{translator.get('io_err_export_no_exist')} '{ruta_limpia}'"
    
    resultado = []
    for root, dirs, files in os.walk(ruta_limpia):
        if '.godot' in dirs: dirs.remove('.godot')
        if '__pycache__' in dirs: dirs.remove('__pycache__')
        
        for archivo in files:
            if archivo in ARCHIVOS_ESPECIALES or any(archivo.endswith(ext) for ext in EXTENSIONES_VALIDAS):
                ruta_completa = os.path.join(root, archivo)
                ruta_norm = ruta_completa.replace('\\', '/')
                contenido = leer_archivo_seguro(ruta_completa)
                resultado.append(f"--- FILE: {ruta_norm} ---\n{contenido}")
    
    return "\n\n".join(resultado) if resultado else f"{translator.get('io_warn_empty_folder')} {ruta_limpia}"

def export_all(ruta_base="."):
    from chispita_core.i18n import translator
    ruta_limpia = limpiar_ruta(ruta_base)
    if not os.path.exists(ruta_limpia):
        return f"{translator.get('io_err_export_no_exist')} '{ruta_limpia}'"
    
    resultado = []
    print(f"{translator.get('io_debug_export_all')} {ruta_limpia}")
    
    for root, dirs, files in os.walk(ruta_limpia):
        dirs[:] = [d for d in dirs if d not in ['.godot', '.git', '__pycache__', 'exports', 'venv', 'node_modules']]
        
        for archivo in files:
            if archivo in ARCHIVOS_ESPECIALES or any(archivo.endswith(ext) for ext in EXTENSIONES_VALIDAS):
                ruta_completa = os.path.join(root, archivo)
                ruta_norm = ruta_completa.replace('\\', '/')
                contenido = leer_archivo_seguro(ruta_completa)
                resultado.append(f"--- FILE: {ruta_norm} ---\n{contenido}")
    
    return "\n\n".join(resultado) if resultado else translator.get('io_warn_proj_empty')

def run_git_commit(mensaje, silencioso=False):
    """Ejecuta git add . y git commit -m 'mensaje'."""
    from chispita_core.i18n import translator
    if not mensaje: mensaje = "Auto-commit Chispita"
    
    if not shutil.which("git"):
        if not silencioso: print(translator.get('io_git_no_git'))
        return
        
    if not silencioso: print(translator.get('io_git_verify'))
    try:
        if not os.path.exists(".git"):
            if not silencioso: print(translator.get('io_git_init'))
            subprocess.run(["git", "init"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
        subprocess.run(["git", "add", "."], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except Exception as e:
        if not silencioso: print(f"{translator.get('io_git_fail_init')} {e}")
        return

    if not silencioso: print(f"{translator.get('io_git_commit_exec')} '{mensaje}'")
    try:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        
        subprocess.run(["git", "commit", "-m", mensaje], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        if not silencioso: print(translator.get('io_git_commit_ok'))
    except subprocess.CalledProcessError as e:
        err = e.stderr.decode('utf-8', errors='replace') if e.stderr else ""
        if "nothing to commit" in err or "nada para hacer commit" in err.lower() or "nothing added to commit" in err:
            if not silencioso: print(translator.get('io_git_nothing'))
        else:
            if not silencioso: print(f"{translator.get('io_git_fail_commit')} {err}")
    except Exception as e:
        if not silencioso: print(f"{translator.get('io_git_exc_commit')} {e}")

def get_git_history(cwd):
    """Devuelve una lista de diccionarios con el historial de git."""
    if not shutil.which("git") or not os.path.exists(os.path.join(cwd, ".git")):
        return []
    try:
        # %h: hash corto, %D: referencias (ramas/tags), %s: mensaje, %ad: fecha
        res = subprocess.run(
            ["git", "log", "--all", "--date=short", "--format=%h|%D|%s|%ad"],
            cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8'
        )
        history = []
        for line in res.stdout.strip().split('\n'):
            if not line: continue
            parts = line.split('|', 3)
            if len(parts) == 4:
                history.append({
                    "hash": parts[0].strip(),
                    "refs": parts[1].strip(),
                    "msg": parts[2].strip(),
                    "date": parts[3].strip()
                })
        return history
    except Exception:
        return []

def is_git_clean(cwd):
    """Comprueba si el directorio de trabajo está limpio."""
    try:
        res = subprocess.run(["git", "status", "--porcelain"], cwd=cwd, stdout=subprocess.PIPE, text=True, encoding='utf-8')
        return len(res.stdout.strip()) == 0
    except:
        return True

def get_current_branch(cwd):
    try:
        res = subprocess.run(["git", "branch", "--show-current"], cwd=cwd, stdout=subprocess.PIPE, text=True, encoding='utf-8')
        return res.stdout.strip()
    except:
        return ""

def checkout_commit_as_branch(cwd, commit_hash, branch_name):
    """Crea una nueva rama desde un commit y cambia a ella."""
    try:
        subprocess.run(["git", "checkout", "-b", branch_name, commit_hash], cwd=cwd, check=True, stderr=subprocess.PIPE)
        return True, ""
    except subprocess.CalledProcessError as e:
        return False, e.stderr.decode('utf-8', errors='replace') if e.stderr else "Error desconocido"

def checkout_main_branch(cwd):
    """Vuelve a la rama main o master."""
    try:
        for branch in ["main", "master"]:
            res = subprocess.run(["git", "rev-parse", "--verify", branch], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res.returncode == 0:
                subprocess.run(["git", "checkout", branch], cwd=cwd, check=True, stderr=subprocess.PIPE)
                return True, ""
        return False, "No se encontró rama main ni master."
    except subprocess.CalledProcessError as e:
        return False, e.stderr.decode('utf-8', errors='replace') if e.stderr else "Error al cambiar de rama."