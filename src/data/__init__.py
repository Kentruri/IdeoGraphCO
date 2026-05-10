"""Módulo de datos: scraping, dataset y datamodule.

Los imports pesados (IdeoGraphDataModule, IdeoGraphDataset) se hacen
de forma lazy para no cargar PyTorch/Lightning al usar solo el scraper.
"""

__all__ = ["IdeoGraphDataModule", "IdeoGraphDataset"]


def __getattr__(name: str):
    if name == "IdeoGraphDataModule":
        from src.data.datamodule import IdeoGraphDataModule
        return IdeoGraphDataModule
    if name == "IdeoGraphDataset":
        from src.data.dataset import IdeoGraphDataset
        return IdeoGraphDataset
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
