"""
Smart Sugarcane Irrigation Advisory System - run this file.

    python main.py

Only the Python standard library is used (tkinter, sqlite3, threading ...).
The first run creates sugarcane.db with demo data. Delete it to start fresh.
"""
import os
import sys

# make sure imports work even if started from another folder
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

from app import main  # noqa: E402

if __name__ == "__main__":
    main()
