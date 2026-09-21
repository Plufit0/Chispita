"""
chispita_core/ops.py  (v2.0)
============================
Operaciones de ordenamiento de sistema de archivos e inventario.

Este módulo agrega a Chispita el dominio "ordenar la PC" sin perder su rol
original de manipular proyectos de código. Todas las operaciones destructivas
soportan dry_run, tope max_affected y quedan registradas en el log persistente
(~/.chispita/chispita.log).

Diseño:
- iter_files() centraliza el recorrido con TODOS los filtros (exclude, only,
  depth, tamaño, fecha, ocultos, junctions). El resto de las operaciones lo
  reutilizan para ser consistentes.
- Cada operación retorna un dict homogéneo:
    {'ok': bool, 'contenido': str, 'results': [ ... ], 'affected': int,
     'blocked': bool}
  'contenido' es lo que se muestra/copia; 'results' alimenta la salida JSON.
"""

import os
import re
import csv
import io
import time
import fnmatch
import hashlib
import shutil
from datetime import datetime

# --- Papelera de reciclaje (opcional, con fallback) ---
try:
    from send2trash import send2trash
    _HAY_SEND2TRASH = True
except Exception:
    _HAY_SEND2TRASH = False

# Tope de seguridad por defecto para operaciones destructivas en masa.
MAX_AFFECTED_DEFAULT = 100

# Carpetas que nunca conviene recorrer al inventariar (ruido / bucles).
IGNORAR_SIEMPRE = {'.git', '.godot', '__pycache__'}


# ==========================================================================
#  PARSEO DE UNIDADES
# ==========================================================================
def parse_size(texto):
    """'50MB' -> bytes. Unidades: B, KB, MB, GB, TB. Devuelve None si no aplica."""
    if texto is None:
        return None
    texto = str(texto).strip().upper().replace(' ', '')
    m = re.match(r'^(\d+(?:\.\d+)?)(B|KB|MB|GB|TB)?$', texto)
    if not m:
        return None
    valor = float(m.group(1))
    unidad = m.group(2) or 'B'
    factor = {'B': 1, 'KB': 1024, 'MB': 1024**2, 'GB': 1024**3, 'TB': 1024**4}[unidad]
    return int(valor * factor)


def parse_age(texto):
    """'6m' -> segundos. Unidades: d(día), w(semana), m(mes=30d), y(año=365d)."""
    if texto is None:
        return None
    texto = str(texto).strip().lower().replace(' ', '')
    m = re.match(r'^(\d+(?:\.\d+)?)([dwmy])$', texto)
    if not m:
        return None
    valor = float(m.group(1))
    unidad = m.group(2)
    factor = {'d': 86400, 'w': 604800, 'm': 2592000, 'y': 31536000}[unidad]
    return valor * factor


def human_size(n):
    """1536 -> '1.5 KB'."""
    n = float(n)
    for unidad in ['B', 'KB', 'MB', 'GB', 'TB']:
        if n < 1024 or unidad == 'TB':
            return f"{n:.1f} {unidad}" if unidad != 'B' else f"{int(n)} B"
        n /= 1024


def _bool_mod(mods, clave, default=False):
    v = str(mods.get(clave, '')).strip().lower()
    if v in ('true', '1', 'yes', 'si', 'sí'):
        return True
    if v in ('false', '0', 'no', ''):
        return default if v == '' else False
    return default


def _lista_mod(mods, clave):
    """'*.tmp, node_modules' -> ['*.tmp', 'node_modules']."""
    v = mods.get(clave)
    if not v:
        return []
    return [p.strip() for p in v.split(',') if p.strip()]


# ==========================================================================
#  RECORRIDO CON FILTROS
# ==========================================================================
def _coincide_alguno(nombre, patrones):
    return any(fnmatch.fnmatch(nombre, p) or nombre == p for p in patrones)


def _timestamp(stat, campo):
    if campo == 'atime':
        return stat.st_atime
    if campo == 'ctime':
        return stat.st_ctime
    return stat.st_mtime


def iter_files(base, mods):
    """
    Genera (ruta_completa, os.stat_result) para cada archivo bajo 'base'
    que pasa todos los filtros indicados en 'mods'.
    """
    exclude = _lista_mod(mods, 'exclude')
    only = _lista_mod(mods, 'only')
    include_hidden = _bool_mod(mods, 'include_hidden', False)
    follow = _bool_mod(mods, 'follow_junctions', False)
    depth = mods.get('depth')
    depth = int(depth) if depth not in (None, '') else None
    min_size = parse_size(mods.get('min_size'))
    max_size = parse_size(mods.get('max_size'))
    campo_fecha = (mods.get('by') or 'mtime').strip().lower()
    older = parse_age(mods.get('older_than'))
    newer = parse_age(mods.get('newer_than'))
    ahora = time.time()

    base = os.path.abspath(base)
    base_depth = base.rstrip(os.sep).count(os.sep)

    for root, dirs, files in os.walk(base, topdown=True, followlinks=follow):
        # Profundidad
        nivel = root.rstrip(os.sep).count(os.sep) - base_depth
        if depth is not None and nivel >= depth:
            dirs[:] = []

        # Podar directorios
        podados = []
        for d in dirs:
            if d in IGNORAR_SIEMPRE:
                continue
            if not include_hidden and d.startswith('.'):
                continue
            if exclude and _coincide_alguno(d, exclude):
                continue
            if not follow and os.path.islink(os.path.join(root, d)):
                continue
            podados.append(d)
        dirs[:] = podados

        for nombre in files:
            if not include_hidden and nombre.startswith('.'):
                continue
            if exclude and _coincide_alguno(nombre, exclude):
                continue
            if only and not _coincide_alguno(nombre, only):
                continue
            ruta = os.path.join(root, nombre)
            try:
                st = os.stat(ruta)
            except (OSError, ValueError):
                continue
            if min_size is not None and st.st_size < min_size:
                continue
            if max_size is not None and st.st_size > max_size:
                continue
            edad = ahora - _timestamp(st, campo_fecha)
            if older is not None and edad < older:
                continue
            if newer is not None and edad > newer:
                continue
            yield ruta, st


def _ordenar(items, sort_spec, key_size, key_time, key_name):
    """items: lista de dicts. sort_spec: 'size desc' | 'mtime asc' | 'name'."""
    if not sort_spec:
        return items
    partes = sort_spec.strip().split()
    campo = partes[0].lower()
    desc = len(partes) > 1 and partes[1].lower() == 'desc'
    if campo == 'size':
        keyf = key_size
    elif campo in ('mtime', 'atime', 'ctime', 'date'):
        keyf = key_time
    else:
        keyf = key_name
        desc = len(partes) > 1 and partes[1].lower() == 'desc'
    return sorted(items, key=keyf, reverse=desc)


# ==========================================================================
#  LOG PERSISTENTE
# ==========================================================================
def _log_path():
    base = os.path.join(os.path.expanduser('~'), '.chispita')
    try:
        os.makedirs(base, exist_ok=True)
    except Exception:
        return None
    return os.path.join(base, 'chispita.log')


def registrar_log(accion, cantidad, detalle, estado='ok'):
    """Append-only. Solo para operaciones que modifican el sistema."""
    ruta = _log_path()
    if not ruta:
        return
    ts = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    linea = f"{ts} | {accion} | {cantidad} archivos | {detalle} | {estado}\n"
    try:
        with open(ruta, 'a', encoding='utf-8') as f:
            f.write(linea)
    except Exception:
        pass


# ==========================================================================
#  EXPORT_INVENTORY
# ==========================================================================
def export_inventory(ruta_base, mods):
    ruta = os.path.abspath(ruta_base) if ruta_base else os.path.abspath('.')
    if not os.path.exists(ruta):
        return {'ok': False, 'contenido': f"[ERROR] INVENTORY: '{ruta}' no existe.",
                'results': [], 'affected': 0, 'blocked': False}

    campo_fecha = (mods.get('by') or 'mtime').strip().lower()
    con_hash = _bool_mod(mods, 'hash_sample', False) or (mods.get('hash_algo') is not None)
    hash_algo = (mods.get('hash_algo') or 'md5').strip().lower()

    filas = []
    for archivo, st in iter_files(ruta, mods):
        ext = os.path.splitext(archivo)[1].lower()
        fila = {
            'path': archivo.replace('\\', '/'),
            'size': st.st_size,
            'size_h': human_size(st.st_size),
            'mtime': datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d'),
            'atime': datetime.fromtimestamp(st.st_atime).strftime('%Y-%m-%d'),
            'ext': ext,
        }
        if con_hash:
            fila['hash'] = _hash_archivo(archivo, hash_algo,
                                         sample=_bool_mod(mods, 'hash_sample', False))
        filas.append(fila)

    # group_by (agrega en vez de listar)
    group_by = (mods.get('group_by') or '').strip().lower()
    if group_by == 'extension':
        return _inventory_group_extension(filas, mods)

    filas = _ordenar(
        filas, mods.get('sort') or 'size desc',
        key_size=lambda f: f['size'],
        key_time=lambda f: f['mtime'],
        key_name=lambda f: f['path'].lower(),
    )
    top = mods.get('top')
    if top not in (None, ''):
        filas = filas[:int(top)]

    formato = (mods.get('format') or 'text').strip().lower()
    contenido = _render_inventory(filas, formato, campo_fecha, con_hash)
    contenido = _quizas_output_to(contenido, mods, ruta, prefijo='inventario')

    return {'ok': True, 'contenido': contenido, 'results': filas,
            'affected': len(filas), 'blocked': False}


def _inventory_group_extension(filas, mods):
    agg = {}
    for f in filas:
        e = f['ext'] or '(sin ext)'
        d = agg.setdefault(e, {'ext': e, 'count': 0, 'size': 0})
        d['count'] += 1
        d['size'] += f['size']
    items = list(agg.values())
    items = _ordenar(items, mods.get('sort') or 'size desc',
                     key_size=lambda x: x['size'],
                     key_time=lambda x: x['count'],
                     key_name=lambda x: x['ext'])
    formato = (mods.get('format') or 'text').strip().lower()
    if formato == 'csv':
        contenido = _csv_de([{'extension': i['ext'], 'archivos': i['count'],
                              'bytes': i['size'], 'tamaño': human_size(i['size'])}
                             for i in items])
    elif formato == 'json':
        import json
        contenido = json.dumps(items, ensure_ascii=False, indent=2)
    else:
        lineas = ["--- INVENTARIO POR EXTENSIÓN ---"]
        for i in items:
            lineas.append(f"{i['ext']:>12}  {i['count']:>6} archivos  {human_size(i['size']):>10}")
        contenido = "\n".join(lineas)
    return {'ok': True, 'contenido': contenido, 'results': items,
            'affected': len(items), 'blocked': False}


def _render_inventory(filas, formato, campo_fecha, con_hash):
    if formato == 'csv':
        return _csv_de(filas)
    if formato == 'json':
        import json
        return json.dumps(filas, ensure_ascii=False, indent=2)
    # texto
    lineas = [f"--- INVENTARIO ({len(filas)} archivos) ---"]
    for f in filas:
        extra = f"  {f['hash']}" if con_hash and f.get('hash') else ""
        lineas.append(f"{f['size_h']:>10}  {f['mtime']}  {f['path']}{extra}")
    return "\n".join(lineas)


def _csv_de(filas):
    if not filas:
        return ""
    buff = io.StringIO()
    writer = csv.DictWriter(buff, fieldnames=list(filas[0].keys()))
    writer.writeheader()
    for f in filas:
        writer.writerow(f)
    return buff.getvalue()


def _hash_archivo(ruta, algo='md5', sample=False):
    try:
        h = hashlib.new(algo)
    except Exception:
        h = hashlib.md5()
    try:
        with open(ruta, 'rb') as f:
            if sample:
                inicio = f.read(65536)
                h.update(inicio)
                try:
                    f.seek(-65536, os.SEEK_END)
                    h.update(f.read(65536))
                except Exception:
                    pass
            else:
                for bloque in iter(lambda: f.read(1024 * 1024), b''):
                    h.update(bloque)
        return h.hexdigest()
    except Exception:
        return ""


def _quizas_output_to(contenido, mods, ruta, prefijo='export'):
    """Si hay output_to, escribe a exports/<nombre> y devuelve un aviso corto."""
    destino = mods.get('output_to')
    if not destino:
        return contenido
    exports_dir = os.path.join(os.getcwd(), 'exports')
    try:
        os.makedirs(exports_dir, exist_ok=True)
        ruta_salida = os.path.join(exports_dir, destino)
        with open(ruta_salida, 'w', encoding='utf-8', newline='') as f:
            f.write(contenido)
        return f"[OK] Resultado escrito en exports/{destino} ({len(contenido)} bytes)."
    except Exception as e:
        return f"[WARN] No se pudo escribir output_to='{destino}': {e}\n\n{contenido}"


# ==========================================================================
#  EXPORT_SIZES  (peso agregado por carpeta)
# ==========================================================================
def export_sizes(ruta_base, mods):
    ruta = os.path.abspath(ruta_base) if ruta_base else os.path.abspath('.')
    if not os.path.exists(ruta):
        return {'ok': False, 'contenido': f"[ERROR] SIZES: '{ruta}' no existe.",
                'results': [], 'affected': 0, 'blocked': False}

    depth = mods.get('depth')
    depth = int(depth) if depth not in (None, '') else 1
    base_depth = ruta.rstrip(os.sep).count(os.sep)

    # Peso total por cada archivo, atribuido a su carpeta de nivel <= depth.
    pesos = {}
    for archivo, st in iter_files(ruta, {k: v for k, v in mods.items() if k != 'depth'}):
        carpeta = os.path.dirname(archivo)
        # Recortar la carpeta al nivel de profundidad pedido
        partes = carpeta.rstrip(os.sep).split(os.sep)
        corte = base_depth + depth
        carpeta_agg = os.sep.join(partes[:corte + 1]) if len(partes) > corte else carpeta
        d = pesos.setdefault(carpeta_agg, {'carpeta': carpeta_agg.replace('\\', '/'),
                                           'bytes': 0, 'archivos': 0})
        d['bytes'] += st.st_size
        d['archivos'] += 1

    items = list(pesos.values())
    for i in items:
        i['tamaño'] = human_size(i['bytes'])
    items = _ordenar(items, mods.get('sort') or 'size desc',
                     key_size=lambda x: x['bytes'],
                     key_time=lambda x: x['archivos'],
                     key_name=lambda x: x['carpeta'].lower())
    top = mods.get('top')
    if top not in (None, ''):
        items = items[:int(top)]

    formato = (mods.get('format') or 'text').strip().lower()
    if formato == 'csv':
        contenido = _csv_de([{'carpeta': i['carpeta'], 'bytes': i['bytes'],
                              'tamaño': i['tamaño'], 'archivos': i['archivos']} for i in items])
    elif formato == 'json':
        import json
        contenido = json.dumps(items, ensure_ascii=False, indent=2)
    else:
        lineas = [f"--- PESO POR CARPETA (depth {depth}) ---"]
        for i in items:
            lineas.append(f"{i['tamaño']:>10}  {i['archivos']:>6} arch.  {i['carpeta']}")
        contenido = "\n".join(lineas)
    contenido = _quizas_output_to(contenido, mods, ruta, prefijo='sizes')
    return {'ok': True, 'contenido': contenido, 'results': items,
            'affected': len(items), 'blocked': False}


# ==========================================================================
#  EXPORT_DUPLICATES
# ==========================================================================
def export_duplicates(ruta_base, mods):
    ruta = os.path.abspath(ruta_base) if ruta_base else os.path.abspath('.')
    if not os.path.exists(ruta):
        return {'ok': False, 'contenido': f"[ERROR] DUPLICATES: '{ruta}' no existe.",
                'results': [], 'affected': 0, 'blocked': False}

    modo = (mods.get('by') or 'hash').strip().lower()
    hash_algo = (mods.get('hash_algo') or 'md5').strip().lower()
    sample = _bool_mod(mods, 'hash_sample', False)
    if 'min_size' not in mods:
        mods = dict(mods, min_size='1MB')  # default sensato

    # Agrupar primero por (tamaño) para acelerar; luego por hash dentro del grupo.
    por_tam = {}
    for archivo, st in iter_files(ruta, mods):
        por_tam.setdefault(st.st_size, []).append(archivo)

    grupos = {}
    for tam, archivos in por_tam.items():
        if len(archivos) < 2:
            continue
        if modo == 'name':
            for a in archivos:
                clave = (os.path.basename(a).lower(), tam)
                grupos.setdefault(clave, []).append(a)
        else:  # hash
            for a in archivos:
                h = _hash_archivo(a, hash_algo, sample=sample)
                if not h:
                    continue
                grupos.setdefault((h, tam), []).append(a)

    duplicados = {k: v for k, v in grupos.items() if len(v) >= 2}
    results = []
    lineas = [f"--- DUPLICADOS (por {modo}) ---"]
    total_recuperable = 0
    for (clave, tam), archivos in sorted(duplicados.items(), key=lambda kv: kv[0][1], reverse=True):
        recuperable = tam * (len(archivos) - 1)
        total_recuperable += recuperable
        lineas.append(f"\n[{len(archivos)}x] {human_size(tam)} c/u  (recuperable: {human_size(recuperable)})")
        for a in archivos:
            lineas.append(f"   {a.replace(chr(92), '/')}")
        results.append({'clave': str(clave), 'tamaño': tam,
                        'copias': len(archivos),
                        'recuperable': recuperable,
                        'archivos': [a.replace('\\', '/') for a in archivos]})
    if not results:
        lineas.append("(sin duplicados con los filtros dados)")
    else:
        lineas.append(f"\nEspacio total recuperable si se deja 1 copia: {human_size(total_recuperable)}")

    formato = (mods.get('format') or 'text').strip().lower()
    if formato == 'json':
        import json
        contenido = json.dumps(results, ensure_ascii=False, indent=2)
    elif formato == 'csv':
        filas = []
        for r in results:
            for a in r['archivos']:
                filas.append({'grupo': r['clave'], 'copias': r['copias'],
                              'bytes': r['tamaño'], 'archivo': a})
        contenido = _csv_de(filas) if filas else "(sin duplicados)"
    else:
        contenido = "\n".join(lineas)
    contenido = _quizas_output_to(contenido, mods, ruta, prefijo='duplicados')
    return {'ok': True, 'contenido': contenido, 'results': results,
            'affected': len(results), 'blocked': False}


# ==========================================================================
#  UTILIDADES DE SEGURIDAD PARA DESTRUCTIVOS
# ==========================================================================
def _chequear_tope(cantidad, mods, config):
    """Devuelve (permitido, mensaje). Aplica max_affected + confirm."""
    tope = mods.get('max_affected', config.get('max_affected'))
    if tope in (None, ''):
        tope = MAX_AFFECTED_DEFAULT
    tope = int(tope)
    confirm = _bool_mod(mods, 'confirm', False) or _bool_mod(config, 'confirm', False)
    if cantidad > tope and not confirm:
        return False, (f"[BLOQUEADO] La operación afectaría {cantidad} archivos "
                       f"(tope max_affected={tope}). Agregá 'confirm: true' para forzar.")
    return True, ""


def _es_dry_run(mods, config):
    return _bool_mod(mods, 'dry_run', False) or _bool_mod(config, 'dry_run', False)


# ==========================================================================
#  BATCH_MOVE
# ==========================================================================
def batch_move(ruta_destino, lineas, mods, config):
    """
    Dos formas:
      A) ruta_destino = carpeta; 'lineas' = rutas origen (se mueven ahí dentro).
      B) ruta_destino = None; 'lineas' = 'origen -> destino'.
    """
    pares = []  # (origen, destino)
    if ruta_destino:
        destino_dir = os.path.abspath(ruta_destino)
        for origen in lineas:
            o = os.path.abspath(origen)
            pares.append((o, os.path.join(destino_dir, os.path.basename(o))))
    else:
        for l in lineas:
            if '->' not in l:
                continue
            o, d = l.split('->', 1)
            pares.append((os.path.abspath(o.strip()), os.path.abspath(d.strip())))

    permitido, msg = _chequear_tope(len(pares), mods, config)
    if not permitido:
        return {'ok': False, 'contenido': msg, 'results': [], 'affected': 0, 'blocked': True}

    dry = _es_dry_run(mods, config)
    results = []
    lineas_out = [f"--- BATCH_MOVE {'(DRY RUN)' if dry else ''} : {len(pares)} archivos ---"]
    exitos = 0
    for origen, dest in pares:
        estado, detalle = _mover_uno(origen, dest, dry)
        if estado == 'ok':
            exitos += 1
        results.append({'cmd': 'BATCH_MOVE', 'origen': origen.replace('\\', '/'),
                        'destino': dest.replace('\\', '/'), 'status': estado, 'detalle': detalle})
        lineas_out.append(f"  [{estado.upper()}] {origen.replace(chr(92), '/')} -> "
                          f"{dest.replace(chr(92), '/')}" + (f"  ({detalle})" if detalle else ""))

    if not dry:
        registrar_log('BATCH_MOVE', exitos,
                      f"{len(pares)} solicitados -> {ruta_destino or 'mapeo explícito'}",
                      'ok' if exitos == len(pares) else 'parcial')
    return {'ok': True, 'contenido': "\n".join(lineas_out), 'results': results,
            'affected': exitos, 'blocked': False}


def _mover_uno(origen, dest, dry):
    if not os.path.exists(origen):
        return 'error', 'origen no existe'
    if os.path.exists(dest):
        return 'skip', 'destino ya existe'
    if dry:
        return 'ok', 'simulado'
    try:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.move(origen, dest)
        return 'ok', ''
    except Exception as e:
        return 'error', str(e)


# ==========================================================================
#  BATCH_RENAME
# ==========================================================================
def batch_rename(ruta_base, mods, config):
    ruta = os.path.abspath(ruta_base) if ruta_base else os.path.abspath('.')
    patron = mods.get('pattern')
    template = mods.get('template')
    if not patron or not template:
        return {'ok': False, 'contenido': "[ERROR] BATCH_RENAME requiere 'pattern:' y 'template:'.",
                'results': [], 'affected': 0, 'blocked': False}
    try:
        rex = re.compile(patron)
    except re.error as e:
        return {'ok': False, 'contenido': f"[ERROR] pattern inválido: {e}",
                'results': [], 'affected': 0, 'blocked': False}

    candidatos = []
    for archivo, _st in iter_files(ruta, {k: v for k, v in mods.items()
                                          if k not in ('pattern', 'template')}):
        nombre = os.path.basename(archivo)
        m = rex.fullmatch(nombre) or rex.match(nombre)
        if not m:
            continue
        nuevo = template
        for i, g in enumerate(m.groups(), start=1):
            nuevo = nuevo.replace('{' + str(i) + '}', g or '')
        candidatos.append((archivo, os.path.join(os.path.dirname(archivo), nuevo)))

    permitido, msg = _chequear_tope(len(candidatos), mods, config)
    if not permitido:
        return {'ok': False, 'contenido': msg, 'results': [], 'affected': 0, 'blocked': True}

    dry = _es_dry_run(mods, config)
    results = []
    lineas_out = [f"--- BATCH_RENAME {'(DRY RUN)' if dry else ''} : {len(candidatos)} archivos ---"]
    exitos = 0
    for origen, dest in candidatos:
        estado, detalle = _mover_uno(origen, dest, dry)
        if estado == 'ok':
            exitos += 1
        results.append({'cmd': 'BATCH_RENAME', 'origen': origen.replace('\\', '/'),
                        'destino': dest.replace('\\', '/'), 'status': estado, 'detalle': detalle})
        lineas_out.append(f"  [{estado.upper()}] {os.path.basename(origen)} -> "
                          f"{os.path.basename(dest)}" + (f"  ({detalle})" if detalle else ""))
    if not candidatos:
        lineas_out.append("(ningún archivo coincidió con el pattern)")
    if not dry and exitos:
        registrar_log('BATCH_RENAME', exitos, f"pattern={patron} en {ruta}",
                      'ok' if exitos == len(candidatos) else 'parcial')
    return {'ok': True, 'contenido': "\n".join(lineas_out), 'results': results,
            'affected': exitos, 'blocked': False}


# ==========================================================================
#  TRASH  (borrado reversible a Papelera)
# ==========================================================================
def trash(ruta, lineas, mods, config):
    """
    Formas admitidas:
      - ruta = archivo/carpeta puntual.
      - ruta = carpeta + filtros (only/older_than/etc.) -> borra lo que coincide.
      - 'lineas' = varias rutas puntuales.
    """
    objetivos = []
    tiene_filtros = any(k in mods for k in ('only', 'exclude', 'min_size', 'max_size',
                                            'older_than', 'newer_than', 'depth'))
    if ruta:
        ruta_abs = os.path.abspath(ruta)
        if os.path.isdir(ruta_abs) and tiene_filtros:
            objetivos = [a for a, _ in iter_files(ruta_abs, mods)]
        else:
            objetivos = [ruta_abs]
    objetivos += [os.path.abspath(l) for l in lineas]

    permitido, msg = _chequear_tope(len(objetivos), mods, config)
    if not permitido:
        return {'ok': False, 'contenido': msg, 'results': [], 'affected': 0, 'blocked': True}

    dry = _es_dry_run(mods, config)
    results = []
    lineas_out = [f"--- TRASH {'(DRY RUN)' if dry else ''} : {len(objetivos)} objetivos ---"]
    if not _HAY_SEND2TRASH and not dry:
        lineas_out.append("[WARN] 'send2trash' no está instalado: "
                          "instalá con 'pip install send2trash' para borrado reversible.")
    exitos = 0
    for obj in objetivos:
        estado, detalle = _trash_uno(obj, dry)
        if estado == 'ok':
            exitos += 1
        results.append({'cmd': 'TRASH', 'path': obj.replace('\\', '/'),
                        'status': estado, 'detalle': detalle})
        lineas_out.append(f"  [{estado.upper()}] {obj.replace(chr(92), '/')}"
                          + (f"  ({detalle})" if detalle else ""))
    if not objetivos:
        lineas_out.append("(sin objetivos)")
    if not dry and exitos:
        registrar_log('TRASH', exitos, f"{ruta or 'lista'} "
                      + (f"filtros={ {k: mods[k] for k in mods if k in ('only','older_than')} }"
                         if tiene_filtros else ''),
                      'ok' if exitos == len(objetivos) else 'parcial')
    return {'ok': True, 'contenido': "\n".join(lineas_out), 'results': results,
            'affected': exitos, 'blocked': False}


def _trash_uno(obj, dry):
    if not os.path.exists(obj):
        return 'error', 'no existe'
    if dry:
        return 'ok', 'simulado'
    if not _HAY_SEND2TRASH:
        return 'error', 'send2trash no instalado'
    try:
        send2trash(obj)
        return 'ok', ''
    except Exception as e:
        return 'error', str(e)
