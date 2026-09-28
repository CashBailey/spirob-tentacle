#!/usr/bin/env python3
"""SpiRob GUI entry point."""

import sys
import signal

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from spirob.gui.main_window import MainWindow


def main():
    """Main entry point for SpiRob GUI."""
    # Enable high DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # Create application
    app = QApplication(sys.argv)
    app.setApplicationName("SpiRob Control Panel")
    app.setOrganizationName("SpiRob")
    app.setOrganizationDomain("spirob.local")

    # Allow Ctrl+C to kill the app
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # Create and show main window
    window = MainWindow()
    window.show()

    # Run event loop
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
