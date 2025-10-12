import logging
import os

os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("logs/app.log", mode='a', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

def get_logger(name: str):
    return logging.getLogger(name)
