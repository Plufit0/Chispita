# Chispita GUI

**EN:** Chispita is a desktop tool that acts as a bridge between AI assistants (like ChatGPT, Claude, etc.) and your actual project files. You paste the AI's output ("supertext") into Chispita — it executes the file commands, and can extract your project's current state to feed back to the AI, enabling a continuous working loop.

**ES:** Chispita es una herramienta de escritorio que hace de puente entre asistentes de IA (como ChatGPT, Claude, etc.) y los archivos reales de tu proyecto. Pegás el output de la IA ("supertexto"), Chispita ejecuta los comandos, y puede extraer el estado actual del proyecto para devolvérselo a la IA — habilitando un loop de trabajo continuo.

---

## How it works / Cómo funciona

```
AI generates supertext → Chispita executes commands → project files updated
      ↑                                                         |
      └─────────── Chispita exports project data ──────────────┘
```
<img width="954" height="782" alt="imagen" src="https://github.com/user-attachments/assets/d1ff0d08-42e3-49e2-a986-ac2dbcc070a2" />

---

## Installation / Instalación

**EN:**
1. Install Python 3 from [python.org](https://python.org)
2. Open a terminal in the project folder and run:
```
pip install click
```
3. Double-click `gui.py` to launch the app.

**ES:**
1. Instalá Python 3 desde [python.org](https://python.org)
2. Abrí una terminal en la carpeta del proyecto y ejecutá:
```
pip install click
```
3. Hacé doble click en `gui.py` para abrir la aplicación.

---

## Commands / Comandos

| Command | Action |
|---|---|
| `CREAR` | Creates a file |
| `ELIMINAR` | Deletes a file |
| `REPLACE_BLOCK` | Replaces a code block |
| `EXPORT_FILE/FOLDER/ALL` | Extracts project data for the AI |
| `EXPORT_TREE` | Exports the full project file tree |
| `EXPORT_TREE_FOLDERS` | Exports folder structure only (no files) |
| `GIT_COMMIT` | Manual git commit |

---

## Tech stack

Python 3 · Tkinter · Git
