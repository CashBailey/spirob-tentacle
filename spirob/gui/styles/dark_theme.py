"""Dark theme stylesheet for SpiRob GUI.

Color scheme inspired by Catppuccin Mocha palette.
"""

# Color definitions (Catppuccin Mocha inspired)
COLORS = {
    # Base colors
    'base': '#1e1e2e',           # Dark background
    'mantle': '#181825',         # Darker background
    'crust': '#11111b',          # Darkest background
    'surface0': '#313244',       # Surface for cards/panels
    'surface1': '#45475a',       # Lighter surface
    'surface2': '#585b70',       # Even lighter surface

    # Text colors
    'text': '#cdd6f4',           # Primary text
    'subtext0': '#a6adc8',       # Secondary text
    'subtext1': '#bac2de',       # Tertiary text

    # Accent colors
    'blue': '#89b4fa',           # Primary accent
    'sapphire': '#74c7ec',       # Secondary accent
    'sky': '#89dceb',            # Tertiary accent

    # Semantic colors
    'green': '#a6e3a1',          # Success/OK
    'yellow': '#f9e2af',         # Warning
    'peach': '#fab387',          # Caution
    'red': '#f38ba8',            # Error/E-stop
    'maroon': '#eba0ac',         # Error secondary

    # Tendon colors
    'tendon_u': '#89b4fa',       # Blue for U tendon
    'tendon_v': '#a6e3a1',       # Green for V tendon
    'tendon_w': '#fab387',       # Orange for W tendon

    # Border and overlay
    'overlay0': '#6c7086',       # Borders
    'overlay1': '#7f849c',       # Hover borders
}


class DarkTheme:
    """Dark theme stylesheet generator for PyQt6."""

    @staticmethod
    def get_stylesheet() -> str:
        """Generate the complete QSS stylesheet."""
        return f"""
        /* ===== Global ===== */
        QWidget {{
            background-color: {COLORS['base']};
            color: {COLORS['text']};
            font-family: 'Segoe UI', 'SF Pro Display', 'Helvetica Neue', sans-serif;
            font-size: 13px;
        }}

        QMainWindow {{
            background-color: {COLORS['mantle']};
        }}

        /* ===== Group Boxes / Panels ===== */
        QGroupBox {{
            background-color: {COLORS['surface0']};
            border: 1px solid {COLORS['overlay0']};
            border-radius: 8px;
            margin-top: 12px;
            padding: 12px;
            padding-top: 24px;
        }}

        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 12px;
            padding: 0 8px;
            color: {COLORS['subtext1']};
            font-weight: bold;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}

        /* ===== Labels ===== */
        QLabel {{
            background-color: transparent;
            color: {COLORS['text']};
        }}

        QLabel[heading="true"] {{
            font-size: 16px;
            font-weight: bold;
            color: {COLORS['text']};
        }}

        QLabel[subheading="true"] {{
            font-size: 11px;
            color: {COLORS['subtext0']};
        }}

        /* ===== Buttons ===== */
        QPushButton {{
            background-color: {COLORS['surface1']};
            color: {COLORS['text']};
            border: 1px solid {COLORS['overlay0']};
            border-radius: 6px;
            padding: 8px 16px;
            font-weight: 500;
            min-height: 20px;
        }}

        QPushButton:hover {{
            background-color: {COLORS['surface2']};
            border-color: {COLORS['blue']};
        }}

        QPushButton:pressed {{
            background-color: {COLORS['blue']};
            color: {COLORS['base']};
        }}

        QPushButton:disabled {{
            background-color: {COLORS['surface0']};
            color: {COLORS['overlay0']};
            border-color: {COLORS['surface1']};
        }}

        QPushButton[accent="true"] {{
            background-color: {COLORS['blue']};
            color: {COLORS['base']};
            border: none;
        }}

        QPushButton[accent="true"]:hover {{
            background-color: {COLORS['sapphire']};
        }}

        QPushButton[danger="true"] {{
            background-color: {COLORS['red']};
            color: {COLORS['base']};
            border: none;
            font-weight: bold;
        }}

        QPushButton[danger="true"]:hover {{
            background-color: {COLORS['maroon']};
        }}

        /* ===== Sliders ===== */
        QSlider::groove:horizontal {{
            background-color: {COLORS['surface1']};
            height: 8px;
            border-radius: 4px;
        }}

        QSlider::handle:horizontal {{
            background-color: {COLORS['blue']};
            width: 20px;
            height: 20px;
            margin: -6px 0;
            border-radius: 10px;
        }}

        QSlider::handle:horizontal:hover {{
            background-color: {COLORS['sapphire']};
        }}

        QSlider::sub-page:horizontal {{
            background-color: {COLORS['blue']};
            border-radius: 4px;
        }}

        /* ===== Line Edits / Input Fields ===== */
        QLineEdit {{
            background-color: {COLORS['surface0']};
            color: {COLORS['text']};
            border: 1px solid {COLORS['overlay0']};
            border-radius: 6px;
            padding: 8px 12px;
            selection-background-color: {COLORS['blue']};
        }}

        QLineEdit:focus {{
            border-color: {COLORS['blue']};
        }}

        QLineEdit:disabled {{
            background-color: {COLORS['mantle']};
            color: {COLORS['overlay0']};
        }}

        /* ===== Spin Boxes ===== */
        QDoubleSpinBox, QSpinBox {{
            background-color: {COLORS['surface0']};
            color: {COLORS['text']};
            border: 1px solid {COLORS['overlay0']};
            border-radius: 6px;
            padding: 6px 10px;
        }}

        QDoubleSpinBox:focus, QSpinBox:focus {{
            border-color: {COLORS['blue']};
        }}

        QDoubleSpinBox::up-button, QSpinBox::up-button,
        QDoubleSpinBox::down-button, QSpinBox::down-button {{
            background-color: {COLORS['surface1']};
            border: none;
            width: 20px;
        }}

        /* ===== Check Boxes ===== */
        QCheckBox {{
            spacing: 8px;
        }}

        QCheckBox::indicator {{
            width: 20px;
            height: 20px;
            border-radius: 4px;
            border: 2px solid {COLORS['overlay0']};
            background-color: {COLORS['surface0']};
        }}

        QCheckBox::indicator:hover {{
            border-color: {COLORS['blue']};
        }}

        QCheckBox::indicator:checked {{
            background-color: {COLORS['blue']};
            border-color: {COLORS['blue']};
        }}

        /* ===== Combo Boxes ===== */
        QComboBox {{
            background-color: {COLORS['surface0']};
            color: {COLORS['text']};
            border: 1px solid {COLORS['overlay0']};
            border-radius: 6px;
            padding: 6px 12px;
            min-width: 100px;
        }}

        QComboBox:hover {{
            border-color: {COLORS['blue']};
        }}

        QComboBox::drop-down {{
            border: none;
            width: 24px;
        }}

        QComboBox QAbstractItemView {{
            background-color: {COLORS['surface0']};
            border: 1px solid {COLORS['overlay0']};
            border-radius: 6px;
            selection-background-color: {COLORS['surface1']};
        }}

        /* ===== List Widgets ===== */
        QListWidget {{
            background-color: {COLORS['surface0']};
            border: 1px solid {COLORS['overlay0']};
            border-radius: 6px;
            padding: 4px;
        }}

        QListWidget::item {{
            padding: 8px;
            border-radius: 4px;
        }}

        QListWidget::item:hover {{
            background-color: {COLORS['surface1']};
        }}

        QListWidget::item:selected {{
            background-color: {COLORS['blue']};
            color: {COLORS['base']};
        }}

        /* ===== Scroll Bars ===== */
        QScrollBar:vertical {{
            background-color: {COLORS['mantle']};
            width: 12px;
            border-radius: 6px;
        }}

        QScrollBar::handle:vertical {{
            background-color: {COLORS['surface1']};
            border-radius: 6px;
            min-height: 30px;
        }}

        QScrollBar::handle:vertical:hover {{
            background-color: {COLORS['surface2']};
        }}

        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}

        QScrollBar:horizontal {{
            background-color: {COLORS['mantle']};
            height: 12px;
            border-radius: 6px;
        }}

        QScrollBar::handle:horizontal {{
            background-color: {COLORS['surface1']};
            border-radius: 6px;
            min-width: 30px;
        }}

        /* ===== Status Bar ===== */
        QStatusBar {{
            background-color: {COLORS['mantle']};
            color: {COLORS['subtext0']};
            border-top: 1px solid {COLORS['surface0']};
        }}

        /* ===== Menu Bar ===== */
        QMenuBar {{
            background-color: {COLORS['mantle']};
            color: {COLORS['text']};
            border-bottom: 1px solid {COLORS['surface0']};
        }}

        QMenuBar::item {{
            padding: 6px 12px;
        }}

        QMenuBar::item:selected {{
            background-color: {COLORS['surface0']};
        }}

        QMenu {{
            background-color: {COLORS['surface0']};
            border: 1px solid {COLORS['overlay0']};
            border-radius: 6px;
            padding: 4px;
        }}

        QMenu::item {{
            padding: 8px 24px;
            border-radius: 4px;
        }}

        QMenu::item:selected {{
            background-color: {COLORS['surface1']};
        }}

        /* ===== Tool Tips ===== */
        QToolTip {{
            background-color: {COLORS['surface0']};
            color: {COLORS['text']};
            border: 1px solid {COLORS['overlay0']};
            border-radius: 4px;
            padding: 6px 10px;
        }}

        /* ===== Progress Bar ===== */
        QProgressBar {{
            background-color: {COLORS['surface0']};
            border: none;
            border-radius: 4px;
            height: 8px;
            text-align: center;
        }}

        QProgressBar::chunk {{
            background-color: {COLORS['blue']};
            border-radius: 4px;
        }}

        /* ===== Tab Widget ===== */
        QTabWidget::pane {{
            background-color: {COLORS['surface0']};
            border: 1px solid {COLORS['overlay0']};
            border-radius: 6px;
        }}

        QTabBar::tab {{
            background-color: {COLORS['mantle']};
            color: {COLORS['subtext0']};
            padding: 8px 16px;
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
        }}

        QTabBar::tab:selected {{
            background-color: {COLORS['surface0']};
            color: {COLORS['text']};
        }}

        QTabBar::tab:hover {{
            background-color: {COLORS['surface1']};
        }}
        """

    @staticmethod
    def get_estop_active_style() -> str:
        """Get style for active E-Stop button (pulsing red)."""
        return f"""
            QPushButton {{
                background-color: {COLORS['red']};
                color: {COLORS['base']};
                border: 3px solid {COLORS['maroon']};
                border-radius: 12px;
                font-size: 24px;
                font-weight: bold;
            }}
        """

    @staticmethod
    def get_estop_normal_style() -> str:
        """Get style for normal E-Stop button."""
        return f"""
            QPushButton {{
                background-color: {COLORS['surface1']};
                color: {COLORS['red']};
                border: 3px solid {COLORS['red']};
                border-radius: 12px;
                font-size: 24px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {COLORS['red']};
                color: {COLORS['base']};
            }}
        """

    @staticmethod
    def get_tendon_slider_style(color: str) -> str:
        """Get style for a tendon slider with specific color."""
        return f"""
            QSlider::groove:horizontal {{
                background-color: {COLORS['surface1']};
                height: 8px;
                border-radius: 4px;
            }}
            QSlider::handle:horizontal {{
                background-color: {color};
                width: 20px;
                height: 20px;
                margin: -6px 0;
                border-radius: 10px;
            }}
            QSlider::handle:horizontal:hover {{
                background-color: {COLORS['text']};
            }}
            QSlider::sub-page:horizontal {{
                background-color: {color};
                border-radius: 4px;
            }}
        """
