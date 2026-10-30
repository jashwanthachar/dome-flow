import sys
import os

# Ensure the root directory is in sys.path so app.py and modules can be resolved
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app import app

# Vercel Serverless Function entry point
if __name__ == "__main__":
    app.run()
