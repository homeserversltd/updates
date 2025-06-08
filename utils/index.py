import datetime
import sys
import hashlib
import os

def log_message(message, level="INFO"):
    """
    Log a message with a timestamp and level to stdout.
    Args:
        message (str): The message to log.
        level (str): Log level (e.g., 'INFO', 'ERROR').
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}", file=sys.stdout)

