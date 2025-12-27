# app/modules/stopwords.py

"""
Listas de stopwords muy básicas para limpiar el ruido en el análisis de "Top Words".
En un contexto de C2, queremos eliminar el ruido de chat, no los comandos.
Añadimos también ruido común de C2/beacons que no aporta valor.
"""

EN_STOPS = {
    "a", "an", "the", "in", "on", "at", "is", "are", "was", "were", "to", "of",
    "and", "or", "but", "for", "with", "from", "by", "as", "it", "its", "i",
    "me", "my", "you", "your", "he", "his", "she", "her", "we", "our", "they",
    "their", "that", "this", "these", "those", "what", "which", "who", "when",
    "where", "why", "how", "not", "no", "yes", "ok", "true", "false", "none",
    "null", "http", "https", "www", "com", "id", "get", "new", "user", "file",
    "data", "bot"
}

ES_STOPS = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "en",
    "es", "son", "con", "por", "para", "sin", "sobre", "que", "qué", "al",
    "se", "su", "sus", "y", "o", "u", "pero", "mas", "más", "mi", "mis", "si"
}

RU_STOPS = {
    "и", "в", "во", "не", "на", "я", "он", "она", "они", "мы", "вы", "то",
    "что", "как", "по", "с", "со", "к", "ко", "от", "из", "за", "для", "до",
    "а", "но", "да", "нет", "это", "этот", "эта", "эти", "тот", "та"
}



# Combinación global
COMMON_STOPS = EN_STOPS.union(ES_STOPS).union(RU_STOPS)