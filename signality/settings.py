"""Loads settings from config.yaml and secrets from .env, in one place."""
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

# The project folder (one level up from this file).
ROOT = Path(__file__).resolve().parent.parent

load_dotenv(ROOT / ".env")


def load_config(path=ROOT / "config.yaml"):
    """Read config.yaml and return it as a dictionary."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def secret(name):
    """Read a secret from .env. Returns None if it isn't set."""
    value = os.getenv(name, "").strip()
    return value or None
