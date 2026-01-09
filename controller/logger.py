import time

def log(module: str, msg: str, level: str = "INFO"):
    """Log a message with timestamp and module name."""
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] [{level:5}] [{module:6}] {msg}")

def info(module: str, msg: str):
    log(module, msg, "INFO")

def warn(module: str, msg: str):
    log(module, msg, "WARN")

def error(module: str, msg: str):
    log(module, msg, "ERROR")
