import os
import click
import sys
import io

# --- FIX CRÍTICO: Forzar salida UTF-8 en consolas Windows ---
# Esto evita el crash cuando Python intenta imprimir emojis o caracteres especiales
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        # Fallback para versiones antiguas de Python
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
# -----------------------------------------------------------

from datetime import datetime
from chispita_core.parser import parsear_supertexto
from chispita_core.io import (
    crear_archivo, eliminar_archivo, replace_block, 
    export_file, export_folder, export_all, run_git_commit, generar_arbol
)

@click.command()
@click.argument('archivo_supertexto')
def chispita_cli(archivo_supertexto):
    """Procesa un archivo SUPER TEXTO para manipular archivos de un proyecto."""
    try:
        with open(archivo_supertexto, 'r', encoding='utf-8') as f:
            contenido = f.read()
        
        comandos = parsear_supertexto(contenido)
        from chispita_core.i18n import translator
        if not comandos:
            print(translator.get('cli_no_cmds'))
            return
        
        print(f"{translator.get('cli_executing')} {len(comandos)} {translator.get('cli_ops')}")
        exports_a_guardar = []
        commit_manual_realizado = False
        contador_comandos = {}
        comandos_modificadores = ['CREAR', 'ELIMINAR', 'REPLACE_BLOCK']
        resumen_exitos = {}
        
        for cmd in comandos:
            c_type = cmd['comando']
            ruta = cmd['ruta']
            contador_comandos[c_type] = contador_comandos.get(c_type, 0) + 1
            
            try:
                exito = False
                tipo_resumen = None

                if c_type == 'CREAR':
                    if crear_archivo(ruta, cmd['contenido']):
                        exito = True
                        tipo_resumen = 'CREADO'
                
                elif c_type == 'ELIMINAR':
                    if eliminar_archivo(ruta):
                        exito = True
                        tipo_resumen = 'ELIMINADO'
                
                elif c_type == 'REPLACE_BLOCK':
                    if replace_block(ruta, cmd['contenido_old'], cmd['contenido_new']):
                        exito = True
                        tipo_resumen = 'REEMPLAZADO'
                
                elif c_type.startswith('EXPORT_'):
                    print(f"{translator.get('cli_prep_export')} {c_type} para {ruta or '.'}")
                    contenido_export = None
                    if c_type == 'EXPORT_FOLDER':
                        contenido_export = export_folder(ruta)
                    elif c_type == 'EXPORT_ALL':
                        r = ruta if ruta else "."
                        contenido_export = export_all(r)
                    elif c_type == 'EXPORT_FILE':
                        rutas = [r.strip() for r in ruta.split(';') if r.strip()]
                        resultados_individuales = [export_file(r) for r in rutas]
                        contenido_export = "\n\n".join(resultados_individuales)
                    elif c_type == 'EXPORT_TREE':
                        r = ruta if ruta and ruta != "." else "."
                        arbol = generar_arbol(r, solo_carpetas=False)
                        contenido_export = f"--- ÁRBOL DE PROYECTO ---\n{arbol}"
                    elif c_type == 'EXPORT_TREE_FOLDERS':
                        r = ruta if ruta and ruta != "." else "."
                        arbol = generar_arbol(r, solo_carpetas=True)
                        contenido_export = f"--- ÁRBOL (SOLO CARPETAS) ---\n{arbol}"
                    
                    if contenido_export:
                        exports_a_guardar.append({'tipo': c_type, 'contenido': contenido_export})
                
                elif c_type == 'GIT_COMMIT':
                    mensaje = ruta if ruta and ruta != "." else "Guardado manual Chispita"
                    run_git_commit(mensaje, silencioso=False)
                    commit_manual_realizado = True

                if exito and tipo_resumen:
                    if tipo_resumen not in resumen_exitos:
                        resumen_exitos[tipo_resumen] = []
                    resumen_exitos[tipo_resumen].append(ruta)

            except Exception as e_cmd:
                print(f"{translator.get('cli_fail_cmd')} {c_type} ({ruta}): {e_cmd}")

        for tipo, archivos in resumen_exitos.items():
            if archivos:
                print(f"[OK] {tipo} ({len(archivos)}): {'; '.join(archivos)}")

        comandos_ejecutados = [cmd for cmd in comandos_modificadores if cmd in contador_comandos]
        if not commit_manual_realizado and comandos_ejecutados:
            resumen = "; ".join([f"{v} {k}" for k, v in contador_comandos.items() if k in comandos_modificadores])
            mensaje_auto = f"Chispita: {resumen}"
            try:
                run_git_commit(mensaje_auto, silencioso=True)
            except Exception as e_git:
                print(f"{translator.get('cli_auto_commit_fail')} {e_git}")

        print(translator.get('cli_done'))
        
        if exports_a_guardar:
            import json
            temp_path = os.path.join(os.path.dirname(__file__), "temp_exports.json")
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(exports_a_guardar, f)

    except FileNotFoundError:
        from chispita_core.i18n import translator
        print(f"{translator.get('cli_err_temp')} {archivo_supertexto}")
    except Exception as e:
        from chispita_core.i18n import translator
        print(f"{translator.get('cli_err_unhandled')} {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    chispita_cli()