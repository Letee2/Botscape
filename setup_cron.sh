#!/bin/bash
Bash

#!/bin/bash

echo "🤖 Configurando cron jobs para Botscape..."

SCRIPT_DIR=$(pwd)
PYTHON_PATH=$(which python3)

if [ -z "$PYTHON_PATH" ]; then
    echo "❌ Error: 'python3' no encontrado."
    exit 1
fi

# --- COMANDOS ACTUALIZADOS ---
# Usamos 'cd' para situarnos en la raíz y ejecutar como módulo (-m)
# Esto asegura que los imports 'from botscape...' funcionen.

# Watchdog (ahora está en services/listener)
WATCHDOG_CMD="cd $SCRIPT_DIR && $PYTHON_PATH -m botscape.services.listener.watchdog >> $SCRIPT_DIR/logs/watchdog.log 2>&1"
WATCHDOG_JOB="*/30 * * * * $WATCHDOG_CMD"

# Health Reporter
HEALTH_CMD="cd $SCRIPT_DIR && $PYTHON_PATH -m botscape.scripts.health_reporter >> $SCRIPT_DIR/logs/health_reporter.log 2>&1"
HEALTH_JOB="*/5 * * * * $HEALTH_CMD"

# Janitor
JANITOR_CMD="cd $SCRIPT_DIR && $PYTHON_PATH -m botscape.scripts.janitor >> $SCRIPT_DIR/logs/janitor.log 2>&1"
JANITOR_JOB="5 3 * * * $JANITOR_CMD"

# Hunter
HUNTER_CMD="cd $SCRIPT_DIR && $PYTHON_PATH -m botscape.scripts.hunter >> $SCRIPT_DIR/logs/hunter.log 2>&1"
HUNTER_JOB="5 4 * * * $HUNTER_CMD"

# Asegurar que exista el directorio de logs
mkdir -p $SCRIPT_DIR/logs

# --- 3. Función para añadir el job si no existe ---
add_cron_job() {
    local job_string="$1"
    local job_name="$2"

    # (crontab -l 2>/dev/null) obtiene el crontab actual, manejando el caso de que esté vacío
    # (grep -qF "...") busca la línea exacta, en silencio
    # || (significa "si el grep falla"...)
    # (crontab -l ...; echo "...") coge el crontab actual Y añade la nueva línea
    # | crontab - ... y carga esa nueva lista como el nuevo crontab.
    
    if (crontab -l 2>/dev/null | grep -qF "$job_string"); then
        echo "✅ El cron job para '$job_name' ya existe. Omitiendo."
    else
        echo "-> Añadiendo cron job para '$job_name'..."
        (crontab -l 2>/dev/null; echo "$job_string") | crontab -
        if [ $? -eq 0 ]; then
            echo "   ... Hecho."
        else
            echo "   ❌ Error al añadir el cron job. ¿Tienes permisos?"
        fi
    fi
}

# --- 4. Ejecutar ---
add_cron_job "$WATCHDOG_JOB" "Watchdog (Salud Listener)"
add_cron_job "$HEALTH_JOB" "Health Reporter (Monitor Disco)"
add_cron_job "$JANITOR_JOB" "Janitor (Limpieza Diaria)" # <-- AÑADIDO
add_cron_job "$HUNTER_JOB" "Hunter (Descubrimiento VT)"

echo ""
echo "🎉 Configuración de Cron finalizada."
echo "Puedes verificar los jobs con el comando: crontab -l"