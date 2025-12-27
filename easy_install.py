import os
import sys
import subprocess
import platform
import shutil
from pathlib import Path

# --- CONFIGURACIÓN VISUAL ---
COLORS = {
    "HEADER": "\033[95m",
    "BLUE": "\033[94m",
    "CYAN": "\033[96m",
    "GREEN": "\033[92m",
    "WARNING": "\033[93m",
    "FAIL": "\033[91m",
    "ENDC": "\033[0m",
    "BOLD": "\033[1m",
}

ASCII_ART = f"""{COLORS['CYAN']}
  ____   ___ _____ ____   ____    _    ____  _____ 
 | __ ) / _ \_   _/ ___| / ___|  / \  |  _ \| ____|
 |  _ \| | | || | \___ \| |     / _ \ | |_) |  _|  
 | |_) | |_| || |  ___) | |___ / ___ \|  __/| |___ 
 |____/ \___/ |_| |____/ \____/_/   \_\_|   |_____|
{COLORS['ENDC']}
      {COLORS['BOLD']}>> Threat Intelligence Platform v1.0 <<{COLORS['ENDC']}
"""

def print_step(msg):
    print(f"\n{COLORS['HEADER']}➤ {msg}{COLORS['ENDC']}")

def print_success(msg):
    print(f"{COLORS['GREEN']}✔ {msg}{COLORS['ENDC']}")

def print_info(msg):
    print(f"{COLORS['BLUE']}ℹ {msg}{COLORS['ENDC']}")

def ask(question, default=None, secret=False):
    """Pregunta al usuario con estilo."""
    prompt = f"{COLORS['BOLD']}{question}{COLORS['ENDC']}"
    if default:
        prompt += f" [{default}]"
    prompt += ": "
    
    while True:
        value = input(prompt).strip()
        if not value and default:
            return default
        if value:
            return value
        print(f"{COLORS['WARNING']}⚠ Este campo es obligatorio.{COLORS['ENDC']}")

# --- HELPERS DE SISTEMA ---

def get_venv_python():
    """Devuelve la ruta del ejecutable de Python dentro del venv."""
    if platform.system() == "Windows":
        return os.path.join("venv", "Scripts", "python.exe")
    return os.path.join("venv", "bin", "python")

def get_venv_pip():
    """Devuelve la ruta del ejecutable de Pip dentro del venv."""
    if platform.system() == "Windows":
        return os.path.join("venv", "Scripts", "pip.exe")
    return os.path.join("venv", "bin", "pip")

def run_command(cmd_list, shell=False):
    """Ejecuta un comando de sistema controlando errores."""
    try:
        subprocess.run(cmd_list, check=True, shell=shell)
    except subprocess.CalledProcessError:
        print(f"{COLORS['FAIL']}❌ Error ejecutando: {' '.join(cmd_list)}{COLORS['ENDC']}")
        sys.exit(1)

# --- PASOS DE INSTALACIÓN ---

def step_1_welcome():
    print(ASCII_ART)
    print("👋 ¡Bienvenido al asistente de despliegue de Botscape!")
    print("Vamos a configurar tu entorno de Threat Hunting en unos minutos.\n")

def step_2_environment_config():
    print_step("Configuración del Entorno (.env)")
    
    print_info("Primero, definamos la arquitectura de tu despliegue.")
    print("1. **Todo en Uno (Local):** Base de datos, Listener y Dashboard en ESTA máquina.")
    print("2. **Híbrido (Remoto):** La Base de datos/Listener están en un Servidor, y este es tu PC de control.")
    
    mode = ask("Elige tu modo (1 o 2)", "1")
    
    config = {}
    
    # --- Base de Datos ---
    config["DB_PORT"] = "5432"
    config["DB_NAME"] = ask("Nombre de la Base de Datos", "botscape_db")
    config["DB_USER"] = ask("Usuario de la Base de Datos", "botscape_user")
    config["DB_PASS"] = ask("Contraseña de la Base de Datos", "botscape_pass")
    
    if mode == "1":
        config["DB_HOST"] = "localhost"
        print_success("Modo Local seleccionado. DB Host fijado a 'localhost'.")
    else:
        config["DB_HOST"] = ask("Introduce la IP de tu Servidor Remoto")
        print_success(f"Modo Remoto seleccionado. Conectando a {config['DB_HOST']}.")

    # --- Telegram ---
    print("\n🔐 Credenciales de Telegram (https://my.telegram.org)")
    config["TELEGRAM_API_ID"] = ask("Tu API ID")
    config["TELEGRAM_API_HASH"] = ask("Tu API HASH")
    config["FORWARDER_BOT_TOKEN"] = ask("Token del Bot (Forwarder)")
    config["TARGET_CHANNEL"] = ask("ID del Canal de Alertas")

    # --- APIs Externas ---
    print("\n🌍 APIs de Inteligencia")
    config["VT_API_KEY"] = ask("VirusTotal API Key (Opcional)", "sk-...")

    # --- OpSec ---
    print("\n🛡️  Seguridad Operacional (OpSec)")
    config["FORBIDDEN_COUNTRY"] = ask("Código de país prohibido (Kill Switch)", "ES")

    # Escribir .env
    with open(".env", "w", encoding="utf-8") as f:
        f.write("# Generado por easy_install.py\n")
        for key, value in config.items():
            f.write(f"{key}={value}\n")
    
    print_success("Archivo .env generado correctamente.")

def step_3_python_setup():
    print_step("Preparando Entorno Python")
    
    # 1. Crear VENV
    if not os.path.exists("venv"):
        print_info("Creando entorno virtual 'venv'...")
        run_command([sys.executable, "-m", "venv", "venv"])
        print_success("Entorno virtual creado.")
    else:
        print_info("Entorno virtual 'venv' ya existente detectado.")

    venv_py = get_venv_python()
    venv_pip = get_venv_pip()

    # 2. Instalar Dependencias
    print_info("Instalando librerías (esto puede tardar un poco)...")
    
    # --- CORRECCIÓN AQUÍ ---
    # Usamos 'python -m pip' en lugar de 'pip' directo para evitar el error de "Access Denied" en Windows
    run_command([venv_py, "-m", "pip", "install", "--upgrade", "pip"])
    # -----------------------
    
    run_command([venv_pip, "install", "-r", "requirements.txt"])
    print_success("Dependencias instaladas.")

    # 3. Instalar Proyecto en modo Editable
    print_info("Instalando Botscape como paquete local...")
    run_command([venv_pip, "install", "-e", "."])
    print_success("Botscape instalado en modo editable (-e).")

def step_4_docker():
    print_step("Infraestructura Docker (Base de Datos y Listener)")
    
    # Solo sugerimos Docker si estamos en localhost, o si el usuario quiere administrar el remoto desde aquí
    if not shutil.which("docker"):
        print(f"{COLORS['WARNING']}⚠️  Docker no detectado. Saltando paso de contenedores.{COLORS['ENDC']}")
        return

    start_docker = ask("¿Quieres levantar los contenedores (DB + Listener) ahora? (s/n)", "s")
    
    if start_docker.lower() == "s":
        print_info("Levantando stack con Docker Compose...")
        try:
            # Probamos docker compose v2 primero, luego v1
            try:
                run_command(["docker", "compose", "up", "-d", "--build"])
            except:
                run_command(["docker-compose", "up", "-d", "--build"])
            
            print_success("¡Contenedores desplegados y corriendo!")
        except Exception:
            print(f"{COLORS['FAIL']}Hubo un problema arrancando Docker. Revisa que Docker Desktop esté corriendo.{COLORS['ENDC']}")

def step_5_cron():
    print_step("Tareas Programadas (Cron)")
    
    if platform.system() != "Linux":
        print_info("Estás en Windows/Mac. La configuración automática de Cron se omite.")
        print_info("Si necesitas ejecutar tareas programadas, usa el Programador de Tareas o ejecuta los scripts manualmente.")
        return

    setup_cron = ask("¿Quieres configurar los Cron Jobs automáticos (Hunter, Janitor, etc)? (s/n)", "s")
    if setup_cron.lower() == "s":
        print_info("Ejecutando script de configuración de cron...")
        run_command(["chmod", "+x", "setup_cron.sh"])
        run_command(["./setup_cron.sh"], shell=True)
        print_success("Cron jobs configurados.")

def step_6_finish():
    print_step("¡Instalación Completada! 🚀")
    
    venv_act = "venv\\Scripts\\activate" if platform.system() == "Windows" else "source venv/bin/activate"
    
    print(f"""
{COLORS['BOLD']}Todo está listo. Aquí tienes tus siguientes pasos:{COLORS['ENDC']}

1. Activa tu entorno:
   {COLORS['CYAN']}{venv_act}{COLORS['ENDC']}

2. Para iniciar el Dashboard:
   {COLORS['CYAN']}streamlit run botscape/dashboard/Home.py{COLORS['ENDC']}

3. Para buscar nuevos bots(Opcional):
   {COLORS['CYAN']}python botscape/scripts/hunter.py{COLORS['ENDC']}

{COLORS['GREEN']}Happy Hunting! 🕵️‍♂️{COLORS['ENDC']}
""")

def main():
    try:
        step_1_welcome()
        step_2_environment_config()
        step_3_python_setup()
        step_4_docker()
        step_5_cron()
        step_6_finish()
    except KeyboardInterrupt:
        print("\n\nCancelado por el usuario. ¡Hasta luego!")
        sys.exit(0)

if __name__ == "__main__":
    main()