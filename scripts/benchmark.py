"""Benchmark — entrena varios encoders con el mismo dataset.

Lanza secuencialmente entrenamientos usando los configs Hydra de cada modelo
en `configs/model/<alias>.yaml`. Soporta múltiples semillas para distinguir
señal de ruido de muestreo.

Cada training:
- Usa el MISMO split de datos (preferiblemente pre-computado desde disco)
- Usa los MISMOS hiperparámetros base (LR, batch, epochs)
- Guarda checkpoints en logs/checkpoints/<alias>/
- Guarda métricas finales en logs/benchmark/<alias>__seed<N>/metrics.json
- Captura stdout/stderr en logs/benchmark/<alias>__seed<N>/stdout.log

Después de correr, ejecutar scripts/compare_models.py para generar el reporte.

Uso:
    # Default: 3 modelos × 1 semilla = 3 entrenamientos
    python scripts/benchmark.py

    # 3 modelos × 3 semillas = 9 entrenamientos (rigor estadístico)
    python scripts/benchmark.py --seeds 42 43 44

    # Solo 2 modelos
    python scripts/benchmark.py --models confliberto beto

    # Saltar uno ya entrenado
    python scripts/benchmark.py --skip confliberto

    # Smoke test (1 batch por modelo, para validar el pipeline)
    python scripts/benchmark.py --smoke-test

    # Override de epochs
    python scripts/benchmark.py --max-epochs 5
"""

import argparse
import logging
import subprocess
import sys
import time
from pathlib import Path

from src.benchmark.registry import AVAILABLE_MODELS
from src.paths import LOGS_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _run_key(encoder_alias: str, seed: int) -> str:
    """Identificador único de una corrida (encoder × semilla)."""
    return f"{encoder_alias}__seed{seed}"


def run_training(
    encoder_alias: str,
    seed: int,
    extra_overrides: list[str] | None = None,
) -> bool:
    """Lanza un entrenamiento individual con el config del encoder y seed.

    Captura stdout+stderr en logs/benchmark/<alias>__seed<N>/stdout.log.

    Returns:
        True si terminó sin errores, False si falló.
    """
    run_key = _run_key(encoder_alias, seed)

    cmd = [
        sys.executable, "-m", "src.training.train",
        f"model={encoder_alias}",
        f"data.seed={seed}",
        # encoder_alias incluye la semilla para que los checkpoints/métricas
        # no se sobreescriban entre corridas multi-seed
        f"+model.encoder_alias_override={run_key}",
        f"hydra.run.dir=logs/hydra/{run_key}",
    ]
    if extra_overrides:
        cmd.extend(extra_overrides)

    # Directorio de salida del run (logs + métricas)
    run_dir = LOGS_DIR / "benchmark" / run_key
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "stdout.log"

    logger.info("=" * 60)
    logger.info("Lanzando: %s (seed=%d)", encoder_alias, seed)
    logger.info("Log: %s", log_path)
    logger.info("=" * 60)

    start = time.time()
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"# Command: {' '.join(cmd)}\n\n")
        f.flush()
        result = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, check=False)
    duration = time.time() - start

    if result.returncode == 0:
        logger.info(
            "✓ %s terminó exitosamente en %.1f min",
            run_key, duration / 60,
        )
        return True
    else:
        logger.error(
            "✗ %s falló (exit %d) después de %.1f min. Ver: %s",
            run_key, result.returncode, duration / 60, log_path,
        )
        # Mostrar últimas líneas del log para diagnóstico rápido
        try:
            tail = log_path.read_text(encoding="utf-8").splitlines()[-20:]
            logger.error("Últimas líneas del log:\n%s", "\n".join(tail))
        except Exception:
            pass
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark de encoders en español")
    parser.add_argument(
        "--models", nargs="+", choices=AVAILABLE_MODELS, default=AVAILABLE_MODELS,
        help=f"Modelos a entrenar (disponibles: {', '.join(AVAILABLE_MODELS)})",
    )
    parser.add_argument(
        "--skip", nargs="+", default=[],
        help="Modelos a saltar (ej: ya entrenados previamente)",
    )
    parser.add_argument(
        "--seeds", nargs="+", type=int, default=[42],
        help="Semillas para multi-seed (ej: 42 43 44). Default: solo [42]",
    )
    parser.add_argument(
        "--max-epochs", type=int, default=None,
        help="Override max_epochs (ej: 5 para prueba rápida)",
    )
    parser.add_argument(
        "--smoke-test", action="store_true",
        help="Corre fast_dev_run para validar la pipeline (1 batch por modelo)",
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
    if args.smoke_test:
        extra_overrides.append("trainer.fast_dev_run=true")

    total_runs = len(models_to_train) * len(args.seeds)

    print()
    print("=" * 60)
    print("  BENCHMARK IdeoGraphCO")
    print(f"  Modelos: {', '.join(models_to_train)}")
    print(f"  Semillas: {', '.join(map(str, args.seeds))}")
    print(f"  Total corridas: {total_runs}")
    if args.smoke_test:
        print("  Modo: SMOKE TEST (fast_dev_run)")
    if extra_overrides:
        print(f"  Overrides: {extra_overrides}")
    print("=" * 60)
    print()

    results: dict[str, bool] = {}
    total_start = time.time()
    completed = 0

    # Orden: por semilla externo, por modelo interno
    # (así si paras a la mitad, tienes 1 seed completa)
    for seed in args.seeds:
        for encoder_alias in models_to_train:
            completed += 1
            print(f"\n[{completed}/{total_runs}] Corriendo {encoder_alias} con seed {seed}\n")

            success = run_training(encoder_alias, seed, extra_overrides)
            results[_run_key(encoder_alias, seed)] = success

            if not success and not args.continue_on_error:
                logger.error("Deteniendo benchmark.")
                logger.info("Para continuar con los demás: --continue-on-error")
                break
        else:
            continue  # if-else en for-else: ejecuta si no hubo break
        break

    # Resumen final
    total_duration = time.time() - total_start
    print()
    print("=" * 60)
    print("  BENCHMARK COMPLETADO")
    print(f"  Tiempo total: {total_duration / 60:.1f} minutos")
    print()
    for run_key, ok in results.items():
        status = "✓" if ok else "✗"
        print(f"  {status} {run_key}")
    print()
    if not args.smoke_test:
        print("  Siguiente paso: python scripts/compare_models.py")
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()
