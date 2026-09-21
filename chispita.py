import os
import click
import sys
import io
import json

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
from chispita_core import ops

# Comandos que modifican el disco (para auto-commit git y para el log).
COMANDOS_MODIFICADORES = ['CREAR', 'ELIMINAR', 'REPLACE_BLOCK']
# Comandos declarativos nuevos que devuelven contenido para copiar/guardar.
COMANDOS_EXPORT = ('EXPORT_ALL', 'EXPORT_FOLDER', 'EXPORT_FILE', 'EXPORT_TREE',
                   'EXPORT_TREE_FOLDERS', 'EXPORT_INVENTORY', 'EXPORT_SIZES',
                   'EXPORT_DUPLICATES')


def _extraer_config(comandos):
    """Toma los modificadores del bloque ---CONFIG--- (si existe) como flags globales."""
    config = {}
    for cmd in comandos:
        if cmd['comando'] == 'CONFIG':
            config.update(cmd.get('modificadores', {}))
    return config


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

        config = _extraer_config(comandos)
        dry_global = str(config.get('dry_run', '')).strip().lower() in ('true', '1', 'yes', 'si', 'sí')
        formato_global = (config.get('format') or 'text').strip().lower()
        if dry_global:
            print("[INFO] MODO DRY RUN GLOBAL: no se modificará ningún archivo.")

        print(f"{translator.get('cli_executing')} {len(comandos)} {translator.get('cli_ops')}")
        exports_a_guardar = []
        commit_manual_realizado = False
        contador_comandos = {}
        resumen_exitos = {}
        resultados_json = []   # contrato de salida estructurado

        for cmd in comandos:
            c_type = cmd['comando']
            ruta = cmd['ruta']
            mods = cmd.get('modificadores', {})
            lineas = cmd.get('lineas', [])
            contador_comandos[c_type] = contador_comandos.get(c_type, 0) + 1

            try:
                exito = False
                tipo_resumen = None

                if c_type == 'CONFIG':
                    continue

                elif c_type == 'CREAR':
                    if crear_archivo(ruta, cmd['contenido']):
                        exito = True
                        tipo_resumen = 'CREADO'
                        resultados_json.append({'cmd': 'CREAR', 'path': ruta, 'status': 'ok'})

                elif c_type == 'ELIMINAR':
                    if dry_global or str(mods.get('dry_run', '')).lower() in ('true', '1', 'yes', 'si', 'sí'):
                        print(f"[DRY RUN] ELIMINAR simularía borrar: {ruta}")
                        resultados_json.append({'cmd': 'ELIMINAR', 'path': ruta, 'status': 'dry_run'})
                    elif eliminar_archivo(ruta):
                        exito = True
                        tipo_resumen = 'ELIMINADO'
                        resultados_json.append({'cmd': 'ELIMINAR', 'path': ruta, 'status': 'ok'})
                    else:
                        resultados_json.append({'cmd': 'ELIMINAR', 'path': ruta, 'status': 'error'})

                elif c_type == 'REPLACE_BLOCK':
                    if replace_block(ruta, cmd['contenido_old'], cmd['contenido_new']):
                        exito = True
                        tipo_resumen = 'REEMPLAZADO'
                        resultados_json.append({'cmd': 'REPLACE_BLOCK', 'path': ruta, 'status': 'ok'})
                    else:
                        resultados_json.append({'cmd': 'REPLACE_BLOCK', 'path': ruta, 'status': 'error'})

                elif c_type in ('BATCH_MOVE', 'BATCH_RENAME', 'TRASH'):
                    res = _ejecutar_destructivo(c_type, ruta, lineas, mods, config)
                    print(res['contenido'])
                    resultados_json.extend(res.get('results', []))

                elif c_type.startswith('EXPORT_'):
                    print(f"{translator.get('cli_prep_export')} {c_type} para {ruta or '.'}")
                    contenido_export = _ejecutar_export(c_type, ruta, mods, resultados_json)
                    if contenido_export:
                        exports_a_guardar.append({'tipo': c_type, 'contenido': contenido_export})

                elif c_type == 'GIT_COMMIT':
                    mensaje = ruta if ruta and ruta != "." else "Guardado manual Chispita"
                    run_git_commit(mensaje, silencioso=False)
                    commit_manual_realizado = True

                if exito and tipo_resumen:
                    resumen_exitos.setdefault(tipo_resumen, []).append(ruta)

            except Exception as e_cmd:
                print(f"{translator.get('cli_fail_cmd')} {c_type} ({ruta}): {e_cmd}")
                resultados_json.append({'cmd': c_type, 'path': ruta, 'status': 'error', 'error': str(e_cmd)})

        for tipo, archivos in resumen_exitos.items():
            if archivos:
                print(f"[OK] {tipo} ({len(archivos)}): {'; '.join(a for a in archivos if a)}")

        # Auto-commit git (solo si hubo cambios reales y no es dry run)
        comandos_ejecutados = [c for c in COMANDOS_MODIFICADORES if c in contador_comandos]
        if not dry_global and not commit_manual_realizado and comandos_ejecutados:
            resumen = "; ".join([f"{v} {k}" for k, v in contador_comandos.items()
                                 if k in COMANDOS_MODIFICADORES])
            try:
                run_git_commit(f"Chispita: {resumen}", silencioso=True)
            except Exception as e_git:
                print(f"{translator.get('cli_auto_commit_fail')} {e_git}")

        print(translator.get('cli_done'))

        # Contrato de salida JSON (opcional, global)
        if formato_global == 'json' and resultados_json:
            exitosos = sum(1 for r in resultados_json if r.get('status') == 'ok')
            fallidos = sum(1 for r in resultados_json if r.get('status') == 'error')
            resumen_json = {
                'ok': fallidos == 0,
                'executed': len(resultados_json),
                'succeeded': exitosos,
                'failed': fallidos,
                'results': resultados_json,
            }
            print("\n<<<CHISPITA_JSON>>>")
            print(json.dumps(resumen_json, ensure_ascii=False, indent=2))
            print("<<<END_JSON>>>")

        if exports_a_guardar:
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


def _ejecutar_export(c_type, ruta, mods, resultados_json):
    """Devuelve el contenido de texto de un comando EXPORT_*."""
    if c_type == 'EXPORT_FOLDER':
        return export_folder(ruta)
    if c_type == 'EXPORT_ALL':
        return export_all(ruta if ruta else ".")
    if c_type == 'EXPORT_FILE':
        rutas = [r.strip() for r in (ruta or '').split(';') if r.strip()]
        return "\n\n".join(export_file(r) for r in rutas)
    if c_type == 'EXPORT_TREE':
        r = ruta if ruta and ruta != "." else "."
        return f"--- ÁRBOL DE PROYECTO ---\n{generar_arbol(r, solo_carpetas=False)}"
    if c_type == 'EXPORT_TREE_FOLDERS':
        r = ruta if ruta and ruta != "." else "."
        return f"--- ÁRBOL (SOLO CARPETAS) ---\n{generar_arbol(r, solo_carpetas=True)}"
    if c_type == 'EXPORT_INVENTORY':
        res = ops.export_inventory(ruta, mods)
        resultados_json.extend([{'cmd': 'EXPORT_INVENTORY', **r} for r in res['results'][:0]])
        return res['contenido']
    if c_type == 'EXPORT_SIZES':
        return ops.export_sizes(ruta, mods)['contenido']
    if c_type == 'EXPORT_DUPLICATES':
        return ops.export_duplicates(ruta, mods)['contenido']
    return None


def _ejecutar_destructivo(c_type, ruta, lineas, mods, config):
    if c_type == 'BATCH_MOVE':
        return ops.batch_move(ruta, lineas, mods, config)
    if c_type == 'BATCH_RENAME':
        return ops.batch_rename(ruta, mods, config)
    if c_type == 'TRASH':
        return ops.trash(ruta, lineas, mods, config)
    return {'ok': False, 'contenido': f'[ERROR] Comando desconocido: {c_type}', 'results': []}


if __name__ == "__main__":
    chispita_cli()
