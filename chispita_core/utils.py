def unescape_special_sequences(text):
    """Remueve el escape de secuencias especiales para que sean procesables."""
    if text is None:
        return None
    
    # Definimos las etiquetas partidas para evitar que el parser se confunda al leer este archivo
    TAG_OLD = "<<<" + "OLD>>>"
    TAG_NEW = "<<<" + "NEW>>>"
    TAG_END = "<<<" + "END>>>"
    
    # Reemplazamos la versión escapada (\<<<TAG>>>) por la real
    # Nota: Usamos replace simple, asumiendo que el input viene con una sola barra invertida de escape
    text = text.replace("\\" + TAG_OLD, TAG_OLD)
    text = text.replace("\\" + TAG_NEW, TAG_NEW)
    text = text.replace("\\" + TAG_END, TAG_END)
    text = text.replace("\\---", "---")
    
    return text