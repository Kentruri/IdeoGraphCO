from pathlib import Path

# Raíz del proyecto (tres niveles arriba de este archivo: src/core/paths.py)
ROOT = Path(__file__).resolve().parent.parent.parent

# Datos versionados con DVC
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"             # artículos crudos del scraper (post filter)
INTERIM_DIR = DATA_DIR / "interim"     # outputs intermedios (legacy, evitar usar)
PROCESSED_DIR = DATA_DIR / "processed" # splits.json, tensores futuros
SILVER_DIR = DATA_DIR / "silver"       # silver set del LLM-as-a-Judge

# Configuraciones Hydra
CONFIGS_DIR = ROOT / "configs"

# Logs y checkpoints
LOGS_DIR = ROOT / "logs"

# Crear directorios automáticamente si no existen
for _dir in (RAW_DIR, INTERIM_DIR, PROCESSED_DIR, SILVER_DIR, LOGS_DIR):
    _dir.mkdir(parents=True, exist_ok=True)
