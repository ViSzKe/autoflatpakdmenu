#!/usr/bin/env python3

import os
import sys
import shutil
import time
import logging
from pathlib import Path

try:
    import pyinotify
except ImportError as e:
    sys.exit(
        f"Error: pyinotify module not found. Please install it using 'sudo apt install python3-pyinotify'\nDetails: {e}"
    )

# Configure logging with more detailed error reporting
logging.basicConfig(
    level=logging.DEBUG,  # Changed to DEBUG for more detailed logs
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("/var/log/flatpak-menu-sync.log"),
        logging.StreamHandler(sys.stdout),  # Also log to stdout
    ],
)

FLATPAK_DIR = "/var/lib/flatpak/exports/share/applications"
TARGET_DIR = "/usr/share/applications"


def check_directories():
    """Verify that required directories exist and are accessible"""
    if not os.path.exists(FLATPAK_DIR):
        logging.error(f"Flatpak directory does not exist: {FLATPAK_DIR}")
        return False
    if not os.path.exists(TARGET_DIR):
        logging.error(f"Target directory does not exist: {TARGET_DIR}")
        return False
    if not os.access(FLATPAK_DIR, os.R_OK):
        logging.error(f"Cannot read from Flatpak directory: {FLATPAK_DIR}")
        return False
    if not os.access(TARGET_DIR, os.W_OK):
        logging.error(f"Cannot write to target directory: {TARGET_DIR}")
        return False
    return True


def sync_desktop_files():
    try:
        if not check_directories():
            return False

        # Create target directory if it doesn't exist
        Path(TARGET_DIR).mkdir(parents=True, exist_ok=True)

        # Get current files in both directories
        flatpak_files = set(Path(FLATPAK_DIR).glob("*.desktop"))
        target_files = set(Path(TARGET_DIR).glob("org.flatpak.*.desktop"))

        # Copy new files
        for src_file in flatpak_files:
            dst_file = Path(TARGET_DIR) / src_file.name
            if not dst_file.exists():
                try:
                    shutil.copy2(src_file, dst_file)
                    os.chmod(dst_file, 0o644)
                    logging.info(f"Copied new file: {src_file.name}")
                except Exception as e:
                    logging.error(f"Error copying {src_file.name}: {str(e)}")

        # Remove obsolete files
        for target_file in target_files:
            src_file = Path(FLATPAK_DIR) / target_file.name
            if not src_file.exists():
                try:
                    target_file.unlink()
                    logging.info(f"Removed obsolete file: {target_file.name}")
                except Exception as e:
                    logging.error(f"Error removing {target_file.name}: {str(e)}")
        return True
    except Exception as e:
        logging.error(f"Unexpected error in sync_desktop_files: {str(e)}")
        return False


class FlatpakWatcher(pyinotify.ProcessEvent):
    def process_IN_CREATE(self, event):
        if event.name.endswith(".desktop"):
            logging.info(f"New file created: {event.name}")
            sync_desktop_files()

    def process_IN_DELETE(self, event):
        if event.name.endswith(".desktop"):
            logging.info(f"File deleted: {event.name}")
            sync_desktop_files()

    def process_IN_MODIFY(self, event):
        if event.name.endswith(".desktop"):
            logging.info(f"File modified: {event.name}")
            sync_desktop_files()


def create_executable(app_name, run_command):
    """Create executable bash scripts for the apps in /usr/bin"""
    try:
        with open (f"/usr/bin/{app_name}", "w") as file:
            file.write("#!/bin/bash\n")
            file.write(run_command)
        os.chmod(f"/usr/bin/{app_name}", 0o755)
        logging.info(f"Created new executable: /usr/bin/{app_name}")
    
    except Exception as e:
        logging.error(f"Error in create_executable: {str(e)}")


def main():
    try:
        logging.info("Flatpak menu sync service started")

        if not check_directories():
            sys.exit(1)

        # Initialize inotify
        wm = pyinotify.WatchManager()
        mask = pyinotify.IN_CREATE | pyinotify.IN_DELETE | pyinotify.IN_MODIFY

        # Create notifier
        handler = FlatpakWatcher()
        notifier = pyinotify.Notifier(wm, handler)

        # Add watch
        wdd = wm.add_watch(FLATPAK_DIR, mask)
        if FLATPAK_DIR not in wdd or not wdd[FLATPAK_DIR]:
            logging.error(f"Failed to add watch for {FLATPAK_DIR}")
            sys.exit(1)

        # Initial sync
        if not sync_desktop_files():
            logging.error("Initial sync failed")
            sys.exit(1)

        logging.info("Starting watch loop")
        # Start watching
        notifier.loop()
    except Exception as e:
        logging.error(f"Fatal error in main: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
