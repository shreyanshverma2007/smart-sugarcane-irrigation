"""
Smart Sugarcane Irrigation Advisory System - run this file.

    python main.py

Only the Python standard library is used (tkinter, sqlite3, threading ...).
The first run creates sugarcane.db with demo data. Delete it to start fresh.
"""
import importlib.util
import os
import sys
import sysconfig

# make sure imports work even if started from another folder
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

# Standard-library modules this app needs. If a student's own file with the
# same name (e.g. random.py) is found first, Python would load that file
# instead and the app crashes. So we load the real ones from Python itself.
STDLIB_MODULES = ["random", "queue", "threading", "datetime", "functools", "abc", "string"]


def use_real_stdlib_modules():
    stdlib = os.path.normcase(os.path.abspath(sysconfig.get_paths()["stdlib"]))
    for name in STDLIB_MODULES:
        real_file = os.path.join(stdlib, name + ".py")
        if not os.path.exists(real_file):
            continue
        spec = importlib.util.find_spec(name)
        found = os.path.normcase(os.path.abspath(spec.origin)) if spec and spec.origin else ""
        if found and found != os.path.normcase(real_file) and found.endswith(".py"):
            print(f"Note: ignoring '{spec.origin}' (it hides Python's own '{name}' module).")
            real_spec = importlib.util.spec_from_file_location(name, real_file)
            module = importlib.util.module_from_spec(real_spec)
            sys.modules[name] = module
            real_spec.loader.exec_module(module)


use_real_stdlib_modules()

from app import main  # noqa: E402

if __name__ == "__main__":
    main()
