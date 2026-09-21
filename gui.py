import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox, simpledialog
import json
import os
import re
import subprocess
import sys
import threading
import queue
import importlib.util
from datetime import datetime
import hashlib
from chispita_core.i18n import translator

# ==========================================
#   CONFIGURACION DE INTERFAZ
# ==========================================
UI_CONFIG = {
    "window_size": "950x750",
    "pad_outer": 10,
    "pad_inner": 5,
    "input_height": 15,
    "output_height": 12,
    "font_family": "Consolas",
    "font_size": 10,
}

# ==========================================
#   CHEQUEO DE REQUERIMIENTOS
# ==========================================
# Si el nombre del paquete de pip difiere del nombre de importación, mapearlo acá.
IMPORT_OVERRIDES = {}


def _leer_requerimientos(base_dir):
    """Lee requirements.txt y devuelve los nombres de paquete (sin versión)."""
    path = os.path.join(base_dir, "requirements.txt")
    nombres = []
    if not os.path.exists(path):
        return nombres
    try:
        with open(path, "r", encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if not linea or linea.startswith("#"):
                    continue
                nombre = re.split(r"[<>=!~; ]", linea, 1)[0].strip()
                if nombre:
                    nombres.append(nombre)
    except Exception:
        pass
    return nombres


def _nombre_import(pip_name):
    return IMPORT_OVERRIDES.get(pip_name, pip_name.replace("-", "_"))


def detectar_faltantes(base_dir):
    """Devuelve la lista de paquetes de requirements.txt que NO están instalados."""
    faltantes = []
    for pip_name in _leer_requerimientos(base_dir):
        try:
            existe = importlib.util.find_spec(_nombre_import(pip_name)) is not None
        except Exception:
            existe = False
        if not existe:
            faltantes.append(pip_name)
    return faltantes


def _pip_run(paquetes, extra=None):
    """Corre pip install. Devuelve (returncode, salida)."""
    cmd = [sys.executable, "-m", "pip", "install"]
    if extra:
        cmd += extra
    cmd += list(paquetes)
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    salida = proc.stdout.decode("utf-8", errors="replace") if proc.stdout else ""
    return proc.returncode, salida


def instalar_paquetes(paquetes):
    """
    Instala paquetes con estrategia robusta:
      1) Forma normal (funciona en la mayoría, incluidos entornos virtuales).
      2) Si falla, Plan B: 'pip install --user' (para máquinas con líos de
         permisos). --user NO se usa primero porque rompe dentro de venvs.
    Devuelve (ok, salida_combinada).
    """
    code, salida = _pip_run(paquetes)
    if code == 0:
        return True, salida
    code2, salida2 = _pip_run(paquetes, extra=["--user"])
    combinada = salida + "\n--- Plan B (--user) ---\n" + salida2
    return code2 == 0, combinada

class ChispitaGUI:
    def __init__(self, root):
        self.root = root
        self.translator = translator
        self.language = 'es' # Idioma por defecto
        
        self.config_file = "gui_config.json"
        self.history_file = "chispita_history.json"
        self.project_path = tk.StringVar()
        self.last_export = ""
        self.current_exports = []
        self.is_running = False
        self.is_blinking = False
        self.blink_job = None
        self.history_data = {}
        self.recent_projects = []
        self.language_configured = False

        self.load_config()
        # Primer arranque (sin idioma guardado): elegir idioma ANTES de todo,
        # así el cartel de requerimientos ya sale en el idioma correcto.
        if not self.language_configured:
            elegido = self._elegir_idioma_inicial()
            self.language = elegido
            self.translator.set_language(elegido)
            self.save_config()
        else:
            self.translator.set_language(self.language) # Aplicar idioma cargado

        self.setup_window()
        self.load_history()
        self.create_widgets()

        self.msg_queue = queue.Queue()
        self.check_queue()

        # Recién ahora (con idioma ya definido) se chequean los requerimientos.
        self.root.after(300, self.check_requirements)
        
    def _elegir_idioma_inicial(self):
        """Cartel de primer arranque: solo elegir idioma (English / Español)."""
        self.root.withdraw()
        dlg = tk.Toplevel(self.root)
        dlg.title(self.translator.get('lang_chooser_title'))
        dlg.geometry("360x200")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()

        resultado = {'lang': 'es'}

        ttk.Label(dlg, text="Chispita", font=("Segoe UI", 20, "bold")).pack(pady=(26, 2))
        ttk.Label(dlg, text=self.translator.get('lang_chooser_title'),
                  font=("Segoe UI", 10)).pack(pady=(0, 18))

        fr = ttk.Frame(dlg)
        fr.pack()

        def elegir(l):
            resultado['lang'] = l
            dlg.destroy()

        ttk.Button(fr, text="English", width=15, command=lambda: elegir('en')).pack(side=tk.LEFT, padx=8)
        ttk.Button(fr, text="Español", width=15, command=lambda: elegir('es')).pack(side=tk.LEFT, padx=8)

        dlg.protocol("WM_DELETE_WINDOW", lambda: elegir('es'))
        # Centrar sobre la pantalla
        dlg.update_idletasks()
        x = (dlg.winfo_screenwidth() - dlg.winfo_width()) // 2
        y = (dlg.winfo_screenheight() - dlg.winfo_height()) // 2
        dlg.geometry(f"+{x}+{y}")

        self.root.wait_window(dlg)
        self.root.deiconify()
        return resultado['lang']

    def check_requirements(self):
        """Chequea requirements.txt; si falta algo, ofrece instalarlo."""
        base = os.path.dirname(os.path.abspath(__file__))
        faltantes = detectar_faltantes(base)
        if faltantes:
            self._dialogo_requerimientos(faltantes)
        else:
            self.log_output(self.translator.get('req_all_ok'))

    def _dialogo_requerimientos(self, faltantes):
        """Ventana con los requerimientos faltantes + botones Instalar / Ignorar."""
        dlg = tk.Toplevel(self.root)
        dlg.title(self.translator.get('req_dialog_title'))
        dlg.geometry("440x340")
        dlg.transient(self.root)
        dlg.grab_set()

        ttk.Label(dlg, text=self.translator.get('req_missing_header'),
                  font=("Segoe UI", 10, "bold"), wraplength=400,
                  justify=tk.LEFT).pack(anchor=tk.W, padx=16, pady=(16, 8))

        lista = ttk.Frame(dlg)
        lista.pack(fill=tk.X, padx=28)
        for r in faltantes:
            ttk.Label(lista, text=f"•  {r}", font=("Segoe UI", 11)).pack(anchor=tk.W, pady=1)

        estado = ttk.Label(dlg, text="", font=("Segoe UI", 9), wraplength=400,
                           justify=tk.LEFT, foreground="gray")
        estado.pack(anchor=tk.W, padx=16, pady=(12, 0))

        botones = ttk.Frame(dlg)
        botones.pack(side=tk.BOTTOM, fill=tk.X, padx=16, pady=16)
        btn_ignorar = ttk.Button(botones, text=self.translator.get('req_ignore'), command=dlg.destroy)
        btn_ignorar.pack(side=tk.RIGHT)
        btn_instalar = ttk.Button(botones, text=self.translator.get('req_install'))
        btn_instalar.pack(side=tk.RIGHT, padx=8)

        estado_pip = {}

        def worker():
            try:
                ok, salida = instalar_paquetes(faltantes)
                estado_pip['code'] = 0 if ok else 1
                estado_pip['out'] = salida
            except Exception as e:
                estado_pip['code'] = 1
                estado_pip['out'] = str(e)
            estado_pip['done'] = True

        def poll():
            if estado_pip.get('done'):
                base = os.path.dirname(os.path.abspath(__file__))
                aun_faltan = detectar_faltantes(base)
                if not aun_faltan:
                    estado.config(text=self.translator.get('req_install_ok'), foreground="green")
                    self.log_output(self.translator.get('req_install_ok'))
                    dlg.after(1400, dlg.destroy)
                else:
                    estado.config(
                        text=f"{self.translator.get('req_install_partial')} {', '.join(aun_faltan)}",
                        foreground="red")
                    self.log_output(f"{self.translator.get('req_install_partial')} {', '.join(aun_faltan)}")
                    btn_instalar.config(state=tk.NORMAL)
                    btn_ignorar.config(state=tk.NORMAL)
                return
            dlg.after(300, poll)

        def instalar():
            btn_instalar.config(state=tk.DISABLED)
            btn_ignorar.config(state=tk.DISABLED)
            estado.config(text=self.translator.get('req_installing'), foreground="blue")
            self.log_output(self.translator.get('req_log_installing'))
            threading.Thread(target=worker, daemon=True).start()
            dlg.after(300, poll)

        btn_instalar.config(command=instalar)
        self.root.wait_window(dlg)

    def load_history(self):
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self.history_data = json.load(f)
            except Exception as e:
                print(f"[WARN] No se pudo cargar historial: {e}")

    def save_history(self):
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.history_data, f, indent=4)
        except Exception as e:
            print(f"[WARN] No se pudo guardar historial: {e}")
            
    def get_hash(self, text):
        return hashlib.md5(text.encode('utf-8')).hexdigest()
    
    def setup_window(self):
        self.root.title(self.translator.get('window_title'))
        self.root.geometry(UI_CONFIG["window_size"])
    
    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    # Cargar idioma guardado
                    if 'language' in config:
                        self.language = config['language']
                        self.language_configured = True
                        
                    if 'recent_projects' in config:
                        self.recent_projects = config['recent_projects']
                    elif 'last_project' in config and config['last_project']:
                        self.recent_projects = [config['last_project']]
                        
                    if self.recent_projects:
                        self.project_path.set(self.recent_projects[0])
            except: pass
    
    def save_config(self):
        current = self.project_path.get().strip()
        if current:
            if current in self.recent_projects:
                self.recent_projects.remove(current)
            self.recent_projects.insert(0, current)
            self.recent_projects = self.recent_projects[:5]
            
            if hasattr(self, 'combo_project'):
                self.combo_project['values'] = self.recent_projects
                
        config = {
            'last_project': current,
            'recent_projects': self.recent_projects,
            'language': self.language # Guardar idioma actual
        }
        with open(self.config_file, 'w') as f:
            json.dump(config, f)
    
    def create_widgets(self):
        pad_out = UI_CONFIG["pad_outer"]
        pad_in = UI_CONFIG["pad_inner"]
        
        header = ttk.Frame(self.root, padding=(pad_out, pad_out, pad_out, 0))
        header.pack(fill=tk.X)
        
        self.btn_help = ttk.Button(header, text=self.translator.get('help_button'), command=self.show_help)
        self.btn_help.pack(side=tk.LEFT)
        
        top = ttk.Frame(self.root, padding=pad_out)
        top.pack(fill=tk.X)
        
        self.lbl_project = ttk.Label(top, text=self.translator.get('project_label'))
        self.lbl_project.pack(side=tk.LEFT, padx=pad_in)
        
        self.combo_project = ttk.Combobox(top, textvariable=self.project_path, values=self.recent_projects)
        self.combo_project.pack(side=tk.LEFT, padx=pad_in, fill=tk.X, expand=True)
        self.combo_project.bind("<Return>", lambda e: self.save_config())
        self.combo_project.bind("<<ComboboxSelected>>", lambda e: self.save_config())
        
        self.btn_browse = ttk.Button(top, text=self.translator.get('browse_button'), command=self.browse_folder)
        self.btn_browse.pack(side=tk.LEFT, padx=pad_in)
        
        self.btn_open_folder = ttk.Button(top, text=self.translator.get('open_folder_button'), command=self.open_project_folder, width=12)
        self.btn_open_folder.pack(side=tk.LEFT, padx=pad_in)
        
        mid = ttk.Frame(self.root, padding=pad_out)
        mid.pack(fill=tk.BOTH, expand=True)
        
        self.lbl_commands = ttk.Label(mid, text=self.translator.get('commands_label'))
        self.lbl_commands.pack(anchor=tk.W)
        
        self.commands_text = scrolledtext.ScrolledText(mid, height=UI_CONFIG["input_height"], font=(UI_CONFIG["font_family"], UI_CONFIG["font_size"]))
        self.commands_text.pack(fill=tk.BOTH, expand=True, pady=pad_in)
        
        self.btns_frame = ttk.Frame(self.root, padding=pad_out)
        self.btns_frame.pack(fill=tk.X)
        
        self.btn_run = ttk.Button(self.btns_frame, text=self.translator.get('run_button'), command=self.paste_and_execute)
        self.btn_run.pack(side=tk.LEFT, padx=pad_in)
        
        self.btn_copy = ttk.Button(self.btns_frame, text=self.translator.get('copy_button'), command=self.copy_result)
        self.btn_copy.pack(side=tk.LEFT, padx=pad_in)

        self.btn_save_export = ttk.Button(self.btns_frame, text=self.translator.get('save_button'), command=self.save_exports, state=tk.DISABLED)
        self.btn_save_export.pack(side=tk.LEFT, padx=pad_in)
        
        self.btn_menu = ttk.Button(self.btns_frame, text=self.translator.get('menu_button'), command=self.show_menu, width=6)
        self.btn_menu.pack(side=tk.LEFT, padx=pad_in)

        # --- Elementos alineados a la derecha (se empaquetan en orden inverso de aparición) ---
        self.btn_lang = ttk.Button(self.btns_frame, text="ES/EN", command=self.toggle_language, width=6)
        self.btn_lang.pack(side=tk.RIGHT, padx=pad_in)

        self.lbl_status = ttk.Label(self.btns_frame, text=self.translator.get('status_ready'), foreground="gray")
        self.lbl_status.pack(side=tk.RIGHT, padx=pad_in)
        
        out = ttk.Frame(self.root, padding=pad_out)
        out.pack(fill=tk.BOTH, expand=True)
        
        self.lbl_console = ttk.Label(out, text=self.translator.get('console_label'))
        self.lbl_console.pack(anchor=tk.W)
        
        self.output_text = scrolledtext.ScrolledText(out, height=UI_CONFIG["output_height"], state=tk.DISABLED, font=(UI_CONFIG["font_family"], UI_CONFIG["font_size"]))
        self.output_text.pack(fill=tk.BOTH, expand=True, pady=pad_in)

    # --- NUEVA FUNCIÓN PARA CAMBIAR IDIOMA ---
    def toggle_language(self):
        new_lang = 'en' if self.translator.language == 'es' else 'es'
        self.language = new_lang
        self.translator.set_language(new_lang)
        self.update_ui_text()
        self.save_config()

    # --- NUEVA FUNCIÓN PARA ACTUALIZAR TEXTOS ---
    def update_ui_text(self):
        self.root.title(self.translator.get('window_title'))
        self.btn_help.config(text=self.translator.get('help_button'))
        self.lbl_project.config(text=self.translator.get('project_label'))
        self.btn_browse.config(text=self.translator.get('browse_button'))
        self.btn_open_folder.config(text=self.translator.get('open_folder_button'))
        self.lbl_commands.config(text=self.translator.get('commands_label'))
        self.btn_run.config(text=self.translator.get('run_button'))
        self.btn_copy.config(text=self.translator.get('copy_button'))
        if hasattr(self, 'btn_save_export'):
            self.btn_save_export.config(text=self.translator.get('save_button'))
        self.btn_menu.config(text=self.translator.get('menu_button'))
        self.lbl_console.config(text=self.translator.get('console_label'))
        
        if self.is_running:
            self.lbl_status.config(text=self.translator.get('status_running'))
        else:
            self.lbl_status.config(text=self.translator.get('status_ready'))

    def browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.project_path.set(folder)
            self.save_config()
            self.log_output(f"{self.translator.get('log_project_set')} {folder}")

    def open_project_folder(self):
        folder = self.project_path.get().strip()
        if not folder or not os.path.exists(folder):
            messagebox.showwarning(
                self.translator.get('alert_notice_title'), 
                self.translator.get('alert_path_empty')
            )
            return
            
        try:
            if sys.platform == "win32":
                os.startfile(folder)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
            self.log_output(f"{self.translator.get('log_folder_open')} {folder}")
        except Exception as e:
            self.log_output(f"{self.translator.get('log_folder_open_error')} {e}")

    def paste_and_execute(self):
        if self.is_running: return
        try:
            content = self.root.clipboard_get()
            if not isinstance(content, str) or not content.strip():
                raise tk.TclError("Contenido no es texto")
                
            self.commands_text.delete("1.0", tk.END)
            self.commands_text.insert("1.0", content)
            self.start_execution_thread()
        except tk.TclError:
            self.log_output(self.translator.get('log_clipboard_empty'))
        except Exception as e:
            self.log_output(f"{self.translator.get('log_paste_error')} {e}")

    def execute_commands_direct(self):
        if self.is_running: return
        self.start_execution_thread()

    def start_execution_thread(self):
        project = self.project_path.get()
        if not project: 
            return messagebox.showerror(
                self.translator.get('alert_error_title'), 
                self.translator.get('alert_no_project')
            )
        
        commands = self.commands_text.get("1.0", tk.END).strip()
        if not commands: 
            return messagebox.showerror(
                self.translator.get('alert_error_title'), 
                self.translator.get('alert_no_commands')
            )
        
        if "---" not in commands or "<<<END>>>" not in commands:
            self.log_output(self.translator.get('log_invalid_supertext'))
            return
            
        clean_commands = commands.strip()
        cmd_hash = self.get_hash(clean_commands)
        proj_key = os.path.normpath(project)
        
        if proj_key not in self.history_data:
            self.history_data[proj_key] = []
            
        if cmd_hash in self.history_data[proj_key]:
            respuesta = messagebox.askyesno(
                self.translator.get('alert_dejavu_title'), 
                self.translator.get('alert_dejavu_msg')
            )
            if not respuesta:
                self.log_output(self.translator.get('log_dejavu_cancel'))
                return
        else:
            self.history_data[proj_key].append(cmd_hash)
            self.save_history()

        self.is_running = True
        self.btn_run.config(state=tk.DISABLED)
        self.btn_menu.config(state=tk.DISABLED)
        self.btn_lang.config(state=tk.DISABLED) # Deshabilitar botón de idioma
        self.lbl_status.config(text=self.translator.get('status_running'), foreground="blue")
        
        temp_path = os.path.join(os.path.dirname(__file__), "supertexto_temp.txt")
        with open(temp_path, 'w', encoding='utf-8') as f: f.write(commands)
        
        chispita_path = os.path.join(os.path.dirname(__file__), "chispita.py")
        
        thread = threading.Thread(target=self._run_process, args=(chispita_path, temp_path, project, commands))
        thread.daemon = True
        thread.start()

    def _run_process(self, script_path, temp_path, cwd, original_commands):
        try:
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            env["CHISPITA_LANG"] = self.translator.language
            
            res = subprocess.run(
                [sys.executable, script_path, temp_path],
                cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env=env
            )
            
            out_str = res.stdout.decode('utf-8', errors='replace') if res.stdout else ""
            err_str = res.stderr.decode('utf-8', errors='replace') if res.stderr else ""
            
            self.msg_queue.put(("LOG", out_str + err_str))
            
            import re
            if re.search(r'---EXPORT_(ALL|FOLDER|FILE|TREE|TREE_FOLDERS|INVENTORY|SIZES|DUPLICATES)', original_commands):
                self.msg_queue.put(("CHECK_EXPORT", None))
                
        except Exception as e:
            self.msg_queue.put(("LOG", f"[ERROR CRITICO THREAD] {e}"))
        finally:
            self.msg_queue.put(("FINISH", temp_path))

    def check_queue(self):
        try:
            while True:
                msg_type, data = self.msg_queue.get_nowait()
                
                if msg_type == "LOG":
                    self.log_output(data)
                elif msg_type == "CHECK_EXPORT":
                    self.check_and_copy_export()
                elif msg_type == "FINISH":
                    self.is_running = False
                    self.btn_run.config(state=tk.NORMAL)
                    self.btn_menu.config(state=tk.NORMAL)
                    self.btn_lang.config(state=tk.NORMAL) # Rehabilitar botón de idioma
                    self.lbl_status.config(text=self.translator.get('status_ready'), foreground="gray")
                    if os.path.exists(data):
                        try: os.remove(data)
                        except: pass
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.check_queue)

    def check_and_copy_export(self):
        temp_path = os.path.join(os.path.dirname(__file__), "temp_exports.json")
        if os.path.exists(temp_path):
            try:
                import json
                with open(temp_path, 'r', encoding='utf-8') as f:
                    self.current_exports = json.load(f)
                os.remove(temp_path)
                
                if self.current_exports:
                    self.log_output(self.translator.get('log_export_ready'))
                    self.btn_save_export.config(state=tk.NORMAL)
                    self.start_blinking()
            except Exception as e:
                self.log_output(f"{self.translator.get('log_export_read_temp_error')} {e}")

    def start_blinking(self):
        self.is_blinking = True
        self._blink()

    def stop_blinking(self):
        self.is_blinking = False
        if self.blink_job:
            self.root.after_cancel(self.blink_job)
            self.blink_job = None
        self.btn_copy.config(text=self.translator.get('copy_button'))

    def _blink(self):
        if not self.is_blinking:
            self.btn_copy.config(text=self.translator.get('copy_button'))
            return
        current_text = self.btn_copy.cget("text")
        base_text = self.translator.get('copy_button')
        if current_text.islower():
            self.btn_copy.config(text=base_text.upper())
        else:
            self.btn_copy.config(text=base_text.lower())
        self.blink_job = self.root.after(600, self._blink)

    def copy_result(self):
        self.stop_blinking()
        if self.current_exports:
            combined_text = "\n\n".join([item['contenido'] for item in self.current_exports])
            self.root.clipboard_clear()
            self.root.clipboard_append(combined_text)
            self.log_output(self.translator.get('log_mass_copy'))
        elif self.last_export:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.last_export)
            self.log_output(self.translator.get('log_manual_copy'))

    def save_exports(self):
        if not self.current_exports:
            return
            
        exports_dir = os.path.join(os.path.dirname(__file__), "exports")
        os.makedirs(exports_dir, exist_ok=True)
        
        now = datetime.now()
        fecha_base = now.strftime("%m-%d")
        nombre_proyecto = os.path.basename(self.project_path.get())
        nombre_proyecto_sano = "".join(c for c in nombre_proyecto if c.isalnum() or c in (' ', '_')).rstrip()
        prefijo = f"{nombre_proyecto_sano}_" if nombre_proyecto_sano else ""

        for item in self.current_exports:
            tipo_comando = item['tipo']
            contenido = item['contenido']
            tipo_archivo = tipo_comando.replace('EXPORT_', '').lower()
            
            contador = 1
            while True:
                filename = f"{prefijo}{tipo_archivo}_{fecha_base}_{contador:02d}.txt"
                path = os.path.join(exports_dir, filename)
                if not os.path.exists(path): break
                contador += 1
            
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(contenido)
                self.log_output(f"[OK] Export guardado: {filename}")
            except Exception as e:
                self.log_output(f"[ERROR] No se pudo guardar {filename}: {e}")
        
        self.btn_save_export.config(state=tk.DISABLED)

    def show_menu(self):
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label=self.translator.get('menu_copy_guide'), command=self.copy_guide)
        menu.add_separator()
        menu.add_command(label=self.translator.get('menu_export_all'), command=self.export_all)
        menu.add_command(label=self.translator.get('menu_export_folder'), command=self.export_folder_ui)
        menu.add_command(label=self.translator.get('menu_tree_full'), command=self.export_tree)
        menu.add_command(label=self.translator.get('menu_tree_folders'), command=self.export_tree_folders)
        menu.add_separator()
        menu.add_command(label=self.translator.get('menu_ordenar_titulo'), state=tk.DISABLED)
        menu.add_command(label=self.translator.get('menu_inventory'), command=self.export_inventory_ui)
        menu.add_command(label=self.translator.get('menu_sizes'), command=self.export_sizes_ui)
        menu.add_command(label=self.translator.get('menu_duplicates'), command=self.export_duplicates_ui)
        menu.add_separator()
        menu.add_command(label=self.translator.get('menu_git_commit'), command=self.git_commit_ui)
        menu.add_command(label=self.translator.get('menu_git_history'), command=self.git_history_ui)
        menu.add_command(label=self.translator.get('menu_git_main'), command=self.return_to_main_branch_ui)
        menu.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())

    def return_to_main_branch_ui(self):
        project = self.project_path.get().strip()
        if not project or not os.path.isdir(project): return
        
        from chispita_core.io import get_current_branch, checkout_main_branch, is_git_clean, run_git_commit
        
        actual = get_current_branch(project)
        if actual in ["main", "master"]:
            self.log_output(self.translator.get('git_msg_main_already'))
            return
            
        if not is_git_clean(project):
            run_git_commit("Auto-commit al volver a main", silencioso=True)
            self.log_output(self.translator.get('git_err_dirty'))
            
        success, err = checkout_main_branch(project)
        if success:
            self.log_output(self.translator.get('git_msg_main_success'))
        else:
            self.log_output(f"[ERROR] {err}")

    def git_history_ui(self):
        project = self.project_path.get().strip()
        if not project or not os.path.isdir(project):
            messagebox.showwarning(self.translator.get('alert_notice_title'), self.translator.get('alert_path_empty'))
            return

        dialog = self._create_git_history_dialog(project)
        self.root.wait_window(dialog)

    def _create_git_history_dialog(self, project_path):
        from chispita_core.io import get_git_history, is_git_clean, checkout_commit_as_branch, run_git_commit
        import re

        class GitHistoryDialog(tk.Toplevel):
            def __init__(self, parent, path, gui_instance):
                super().__init__(parent)
                self.transient(parent)
                self.grab_set()
                self.gui = gui_instance
                self.path = path
                
                self.title(self.gui.translator.get('dialog_git_history_title'))
                self.geometry("800x450")

                tree_frame = ttk.Frame(self)
                tree_frame.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)

                cols = ("hash", "refs", "msg", "date")
                self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse")
                
                self.tree.heading("hash", text=self.gui.translator.get('git_col_hash'))
                self.tree.heading("refs", text=self.gui.translator.get('git_col_refs'))
                self.tree.heading("msg", text=self.gui.translator.get('git_col_msg'))
                self.tree.heading("date", text=self.gui.translator.get('git_col_date'))
                
                self.tree.column("hash", width=80, stretch=False)
                self.tree.column("refs", width=150, stretch=False)
                self.tree.column("msg", width=450, stretch=True)
                self.tree.column("date", width=100, stretch=False)

                self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

                scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
                scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
                self.tree.configure(yscrollcommand=scrollbar.set)

                button_frame = ttk.Frame(self)
                button_frame.pack(pady=(0, 10), padx=10, fill=tk.X)

                self.btn_travel = ttk.Button(button_frame, text=self.gui.translator.get('git_btn_travel'), command=self.on_travel)
                self.btn_travel.pack(side=tk.LEFT, padx=5)

                close_button = ttk.Button(button_frame, text=self.gui.translator.get('btn_close'), command=self.destroy)
                close_button.pack(side=tk.RIGHT)

                self.populate_tree()

            def populate_tree(self):
                history = get_git_history(self.path)
                for commit in history:
                    self.tree.insert("", tk.END, values=(commit["hash"], commit["refs"], commit["msg"], commit["date"]))

            def on_travel(self):
                selected = self.tree.focus()
                if not selected: return
                
                item = self.tree.item(selected)
                commit_hash = item["values"][0]
                
                if not is_git_clean(self.path):
                    run_git_commit("Auto-commit antes del viaje temporal", silencioso=True)
                    self.gui.log_output(self.gui.translator.get('git_err_dirty'))
                
                branch_name = simpledialog.askstring(
                    self.gui.translator.get('git_prompt_branch_title'),
                    self.gui.translator.get('git_prompt_branch_msg'),
                    parent=self
                )
                
                if not branch_name: return
                
                if not re.match(r'^[a-zA-Z0-9\-_]+$', branch_name):
                    messagebox.showerror("Error", self.gui.translator.get('git_err_branch_name'))
                    return
                    
                success, err = checkout_commit_as_branch(self.path, commit_hash, branch_name)
                if success:
                    self.gui.log_output(f"{self.gui.translator.get('git_msg_travel_success')} {branch_name}")
                    self.destroy()
                else:
                    self.gui.log_output(f"[ERROR] {err}")

        return GitHistoryDialog(self.root, project_path, self)

    def export_folder_ui(self):
        project = self.project_path.get().strip()
        if not project or not os.path.isdir(project):
            messagebox.showwarning(
                self.translator.get('alert_notice_title'), 
                self.translator.get('alert_path_empty')
            )
            return

        dialog = self._create_folder_selector_dialog(project)
        self.root.wait_window(dialog)
        
        folder = dialog.result
        if folder:
            self.commands_text.delete("1.0", tk.END)
            tag_end = "<<<" + "END>>>"
            self.commands_text.insert("1.0", f"---EXPORT_FOLDER:{folder}---\n{tag_end}")
            self.execute_commands_direct()

    def _create_folder_selector_dialog(self, project_path):
        
        class FolderSelectorDialog(tk.Toplevel):
            def __init__(self, parent, path, translator):
                super().__init__(parent)
                self.transient(parent)
                self.grab_set()
                self.result = None
                self.translator = translator
                
                self.title(self.translator.get('dialog_export_folder_title'))
                self.geometry("450x550")

                tree_frame = ttk.Frame(self)
                tree_frame.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)

                self.tree = ttk.Treeview(tree_frame, selectmode="browse")
                self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

                scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
                scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
                self.tree.configure(yscrollcommand=scrollbar.set)

                button_frame = ttk.Frame(self)
                button_frame.pack(pady=(0, 10), padx=10, fill=tk.X)

                ok_button = ttk.Button(button_frame, text=self.translator.get('btn_accept'), command=self.on_ok)
                ok_button.pack(side=tk.RIGHT, padx=5)

                cancel_button = ttk.Button(button_frame, text=self.translator.get('btn_cancel'), command=self.on_cancel)
                cancel_button.pack(side=tk.RIGHT)

                self.path_map = {}
                self.populate_tree(path)
                
                self.tree.bind("<Double-1>", self.on_ok)

            def populate_tree(self, root_path):
                root_node = self.tree.insert("", tk.END, text=os.path.basename(root_path) or root_path, open=True)
                self.path_map[root_node] = root_path
                
                nodes = {root_path: root_node}

                for root, dirs, _ in os.walk(root_path, topdown=True):
                    parent_node_id = nodes.get(root)
                    if not parent_node_id: continue
                    
                    dirs.sort()
                    for d in dirs:
                        full_path = os.path.join(root, d)
                        child_node = self.tree.insert(parent_node_id, tk.END, text=d)
                        self.path_map[child_node] = full_path
                        nodes[full_path] = child_node

            def on_ok(self, event=None):
                selected_item = self.tree.focus()
                if selected_item:
                    full_path = self.path_map.get(selected_item)
                    project_root = self.path_map.get(self.tree.get_children("")[0])
                    
                    relative_path = os.path.relpath(full_path, project_root)
                    
                    if relative_path == ".":
                        self.result = "res://"
                    else:
                        self.result = "res://" + relative_path.replace("\\", "/")
                self.destroy()

            def on_cancel(self):
                self.result = None
                self.destroy()

        return FolderSelectorDialog(self.root, project_path, self.translator)

    def show_help(self):
        messagebox.showinfo(
            self.translator.get('help_dialog_title'),
            self.translator.get('help_dialog_msg')
        )

    def copy_guide(self):
        guide_path = os.path.join(os.path.dirname(__file__), "guia.txt")
        if os.path.exists(guide_path):
            try:
                with open(guide_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.root.clipboard_clear()
                self.root.clipboard_append(content)
                self.log_output(self.translator.get('log_guide_copied'))
            except Exception as e:
                self.log_output(f"[ERROR] {e}")
        else:
            messagebox.showwarning(
                self.translator.get('alert_notice_title'),
                self.translator.get('alert_guide_not_found')
            )

    def export_all(self):
        self.commands_text.delete("1.0", tk.END)
        tag_end = "<<<" + "END>>>"
        self.commands_text.insert("1.0", f"---EXPORT_ALL:.---\n{tag_end}")
        self.execute_commands_direct()

    def export_tree(self):
        self.commands_text.delete("1.0", tk.END)
        tag_end = "<<<" + "END>>>"
        self.commands_text.insert("1.0", f"---EXPORT_TREE:.---\n{tag_end}")
        self.execute_commands_direct()

    def export_tree_folders(self):
        self.commands_text.delete("1.0", tk.END)
        tag_end = "<<<" + "END>>>"
        self.commands_text.insert("1.0", f"---EXPORT_TREE_FOLDERS:.---\n{tag_end}")
        self.execute_commands_direct()

    def _pedir_ruta_absoluta(self, titulo):
        """Pide una ruta absoluta para las operaciones de 'ordenar PC'."""
        ruta = simpledialog.askstring(titulo, self.translator.get('dialog_ordenar_msg'))
        if ruta:
            ruta = ruta.strip().strip('"')
        return ruta

    def export_inventory_ui(self):
        ruta = self._pedir_ruta_absoluta(self.translator.get('dialog_inventory_title'))
        if not ruta:
            return
        self.commands_text.delete("1.0", tk.END)
        tag_end = "<<<" + "END>>>"
        self.commands_text.insert("1.0",
            f"---EXPORT_INVENTORY:{ruta}---\nsort: size desc\ntop: 200\nformat: csv\n{tag_end}")
        self.execute_commands_direct()

    def export_sizes_ui(self):
        ruta = self._pedir_ruta_absoluta(self.translator.get('dialog_sizes_title'))
        if not ruta:
            return
        self.commands_text.delete("1.0", tk.END)
        tag_end = "<<<" + "END>>>"
        self.commands_text.insert("1.0",
            f"---EXPORT_SIZES:{ruta}---\ndepth: 2\nsort: size desc\n{tag_end}")
        self.execute_commands_direct()

    def export_duplicates_ui(self):
        ruta = self._pedir_ruta_absoluta(self.translator.get('dialog_duplicates_title'))
        if not ruta:
            return
        self.commands_text.delete("1.0", tk.END)
        tag_end = "<<<" + "END>>>"
        self.commands_text.insert("1.0",
            f"---EXPORT_DUPLICATES:{ruta}---\nby: hash\nmin_size: 1MB\n{tag_end}")
        self.execute_commands_direct()

    def git_commit_ui(self):
        msg = simpledialog.askstring(
            self.translator.get('dialog_git_commit_title'),
            self.translator.get('dialog_git_commit_msg')
        )
        if msg:
            self.commands_text.delete("1.0", tk.END)
            tag_end = "<<<" + "END>>>"
            self.commands_text.insert("1.0", f"---GIT_COMMIT:{msg}---\n{tag_end}")
            self.execute_commands_direct()

    def log_output(self, text):
        timestamp = datetime.now().strftime("%H:%M:%S")
        text = text.strip()
        if not text: return
        
        formatted_text = f"[{timestamp}] {text}"
        
        self.output_text.config(state=tk.NORMAL)
        self.output_text.insert(tk.END, formatted_text + "\n")
        self.output_text.see(tk.END)
        self.output_text.config(state=tk.DISABLED)

if __name__ == "__main__":
    root = tk.Tk()
    app = ChispitaGUI(root)
    root.mainloop()