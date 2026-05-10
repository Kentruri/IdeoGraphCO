"""Benchmark — entrena ConfliBERT, MarIA y BETO con el mismo dataset.

Lanza secuencialmente 3 entrenamientos usando los configs Hydra:
- model=confliberto
- model=maria
- model=beto

Cada training:
- Usa el MISMO split de datos (semilla fija: cfg.data.seed)
- Usa los MISMOS hiperparámetros base (LR, batch, epochs)
- Guarda checkpoints en logs/checkpoints/<encoder_alias>/
- Guarda métricas finales en logs/benchmark/<encoder_alias>/metrics.json

Después de correr este script, ejecuta scripts/compare_models.py para
generar el reporte comparativo.

Uso:
    python scripts/benchmark.py
    python scripts/benchmark.py --models confliberto beto      # solo 2
    python scripts/benchmark.py --max-epochs 5                  # entrenamiento corto
    python scripts/benchmark.py --skip confliberto              # saltar uno ya hecho
"""

import argparse
import logging
import subprocess
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Modelos disponibles para el benchmark
AVAILABLE_MODELS: list[str] = ["confliberto", "maria", "beto"]


def run_training(
    encoder_alias: str,
    extra_overrides: list[str] | None = None,
) -> bool:
    """Lanza un entrenamiento individual con el config del encoder.

    Returns:
        True si el entrenamiento terminó sin errores, False si falló.
    """
    cmd = [
        sys.executable, "-m", "src.training.train",
        f"model={encoder_alias}",
    ]
    if extra_overrides:
        cmd.extend(extra_overrides)

    logger.info("=" * 60)
    logger.info("Lanzando entrenamiento: %s", encoder_alias)
    logger.info("Comando: %s", " ".join(cmd))
    logger.info("=" * 60)

    start = time.time()
    result = subprocess.run(cmd, check=False)
    duration = time.time() - start

    if result.returncode == 0:
        logger.info(
            "✓ %s terminó exitosamente en %.1f minutos",
            encoder_alias, duration / 60,
        )
        return True
    else:
        logger.error(
            "✗ %s falló con exit code %d después de %.1f min",
            encoder_alias, result.returncode, duration / 60,
        )
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark de 3 encoders en español")
    parser.add_argument(
        "--models", nargs="+", choices=AVAILABLE_MODELS, default=AVAILABLE_MODELS,
        help="Modelos a entrenar (default: los 3)",
    )
    parser.add_argument(
        "--skip", nargs="+", default=[],
        help="Modelos a saltar (ej: ya entrenados previamente)",
    )
    parser.add_argument(
        "--max-epochs", type=int, default=None,
        help="Override max_epochs para todos (ej: 5 para prueba rápida)",
    )
    parser.add_argument(
        "--continue-on-error", action="store_true",
        help="Continuar con los siguientes modelos si uno falla",
    )
    args = parser.parse_args()

    # Filtrar modelos según args
    models_to_train = [m for m in args.models if m not in args.skip]

    if not models_to_train:
        logger.warning("No hay modelos para entrenar (todos saltados).")
        return

    # Overrides comunes
    extra_overrides: list[str] = []
    if args.max_epochs is not None:
        extra_overrides.append(f"trainer.max_epochs={args.max_epochs}")

    print()
    print("=" * 60)
    print("  BENCHMARK IdeoGraphCO — 3 encoders en español")
    print(f"  Modelos: {', '.join(models_to_train)}")
    print(f"  Overrides: {extra_overrides if extra_overrides else 'ninguno'}")
    print("=" * 60)
    print()

    results: dict[str, bool] = {}
    total_start = time.time()

    for encoder_alias in models_to_train:
        success = run_training(encoder_alias, extra_overrides)
        results[encoder_alias] = success

        if not success and not args.continue_on_error:
            logger.error("Deteniendo benchmark debido a error en %s.", encoder_alias)
            logger.info("Para continuar con los demás: --continue-on-error")
            break

    # Resumen final
    total_duration = time.time() - total_start
    print()
    print("=" * 60)
    print("  BENCHMARK COMPLETADO")
    print(f"  Tiempo total: {total_duration / 60:.1f} minutos")
    print()
    for model_name, ok in results.items():
        status = "✓" if ok else "✗"
        print(f"  {status} {model_name}")
    print()
    print("  Siguiente paso: python scripts/compare_models.py")
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()
