from pathlib import Path

# Raíz del proyecto (un nivel arriba de src/)
ROOT = Path(__file__).resolve().parent.parent

# Datos
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"

# Configuraciones
CONFIGS_DIR = ROOT / "configs"

# Logs y checkpoints
LOGS_DIR = ROOT / "logs"

# Crear directorios automáticamente si no existen
for _dir in (RAW_DIR, INTERIM_DIR, PROCESSED_DIR, LOGS_DIR):
    _dir.mkdir(parents=True, exist_ok=True)
