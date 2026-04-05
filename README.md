🇺🇸 [English](#english) · 🇦🇷 [Español](#español)

---

# English

Chispita is a desktop tool that acts as a bridge between AI assistants (like ChatGPT, Claude, etc.) and your actual project files. You paste the AI's output ("supertext") into Chispita — it executes the file commands, and can extract your project's current state to feed back to the AI, enabling a continuous working loop.

## How it works

```
AI generates supertext → Chispita executes commands → project files updated
      ↑                                                         |
      └─────────── Chispita exports project data ──────────────┘
```

## Screenshot

<img width="953" height="783" alt="imagen" src="https://github.com/user-attachments/assets/8fd625cd-38ff-4825-8f45-2601b40586cd" />

## Commands

| Command | Action |
|---|---|
| `CREAR` | Creates a file |
| `ELIMINAR` | Deletes a file |
| `REPLACE_BLOCK` | Replaces a code block |
| `EXPORT_FILE/FOLDER/ALL` | Extracts project data for the AI |
| `EXPORT_TREE` | Exports the full project file tree |
| `EXPORT_TREE_FOLDERS` | Exports folder structure only (no files) |
| `GIT_COMMIT` | Manual git commit |

> **Menu shortcuts:** The Menu button provides quick access to the most common actions — export project, list file/folder tree, Git commit, and Git history with time-travel — without typing any commands manually.

## Installation

1. Install Python 3 from [python.org](https://python.org)
2. Open a terminal in the project folder and run:
```
pip install click
```
3. Double-click `gui.py` to launch the app.

---

# Español

Chispita es una herramienta de escritorio que hace de puente entre asistentes de IA (como ChatGPT, Claude, etc.) y los archivos reales de tu proyecto. Pegás el output de la IA ("supertexto"), Chispita ejecuta los comandos, y puede extraer el estado actual del proyecto para devolvérselo a la IA — habilitando un loop de trabajo continuo.

## Cómo funciona

```
La IA genera supertexto → Chispita ejecuta comandos → archivos del proyecto actualizados
      ↑                                                         |
      └─────────── Chispita exporta datos del proyecto ────────┘
```

## Screenshot

<img width="954" height="782" alt="imagen" src="https://github.com/user-attachments/assets/6ccd0d1c-00a7-47a0-be7a-89c53c0d0673" />



## Comandos

| Comando | Acción |
|---|---|
| `CREAR` | Crea un archivo |
| `ELIMINAR` | Elimina un archivo |
| `REPLACE_BLOCK` | Reemplaza un bloque de código |
| `EXPORT_FILE/FOLDER/ALL` | Extrae datos del proyecto para la IA |
| `EXPORT_TREE` | Exporta el árbol completo de archivos del proyecto |
| `EXPORT_TREE_FOLDERS` | Exporta solo la estructura de carpetas |
| `GIT_COMMIT` | Commit manual de git |

> **Menú de accesos rápidos:** El botón Menú da acceso directo a las acciones más comunes — exportar proyecto, listar árbol de archivos/carpetas, Git commit, e historial de Git con viaje en el tiempo — sin necesidad de escribir comandos.

## Instalación

1. Instalá Python 3 desde [python.org](https://python.org)
2. Abrí una terminal en la carpeta del proyecto y ejecutá:
```
pip install click
```
3. Hacé doble click en `gui.py` para abrir la aplicación.
