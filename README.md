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
