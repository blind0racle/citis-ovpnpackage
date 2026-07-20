import json
import os
import sys

DEFAULT_CONFIG_PATH = "/etc/covpn/config.json"

_config = None

def load_config(config_path=None):
    global _config
    if _config is not None:
        return _config
    path = config_path or DEFAULT_CONFIG_PATH
    if not os.path.exists(path):
        print(f"Error: Config file '{path}' not found.")
        sys.exit(1)
    try:
        with open(path, 'r') as f:
            _config = json.load(f)
    except Exception as e:
        print(f"Error loading config: {e}")
        sys.exit(1)
    return _config

def get_config():
    if _config is None:
        load_config()
    return _config

def get_version():
    cfg = get_config()
    return cfg.get('version', 'unknown')