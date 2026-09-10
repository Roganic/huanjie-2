"""Compatibility import; all save/load routes use the full snapshot service."""
from src.routers.persistence import router, save_game, list_saves, load_by_id as load_save
