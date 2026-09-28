"""Preset panel for saving and loading robot poses."""

import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox,
    QPushButton, QListWidget, QListWidgetItem, QInputDialog,
    QMessageBox, QSizePolicy
)
from PyQt6.QtCore import pyqtSignal, Qt

from spirob.gui.styles.dark_theme import COLORS


@dataclass
class Preset:
    """A saved robot pose."""
    name: str
    u_angle: float = 0.0
    v_angle: float = 0.0
    w_angle: float = 0.0


class PresetPanel(QWidget):
    """Panel for managing preset poses.

    Features:
    - List of saved presets
    - Add current pose as preset
    - Apply preset
    - Delete preset
    """

    preset_selected = pyqtSignal(Preset)  # Emits when preset should be applied

    # Default presets
    DEFAULT_PRESETS = [
        Preset("Home", 0, 0, 0),
        Preset("Curl Left", -90, 45, 0),
        Preset("Curl Right", 90, -45, 0),
        Preset("Extend", 180, 0, 180),
        Preset("Wrap", -180, -180, -180),
    ]

    def __init__(self, config_path: Optional[str] = None, parent=None):
        """Initialize preset panel.

        Args:
            config_path: Path to save/load presets (None for no persistence)
            parent: Parent widget
        """
        super().__init__(parent)

        self._config_path = config_path
        self._presets: List[Preset] = []
        self._current_positions: Dict[str, float] = {'u': 0, 'v': 0, 'w': 0}

        self._setup_ui()
        self._load_presets()

    def _setup_ui(self):
        """Set up the UI."""
        group = QGroupBox("Presets")
        group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(group)

        # Preset list
        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self._list)

        # Buttons row 1
        btn_row1 = QHBoxLayout()

        self._add_btn = QPushButton("+ Add Current")
        self._add_btn.clicked.connect(self._on_add_clicked)
        btn_row1.addWidget(self._add_btn)

        self._apply_btn = QPushButton("Apply")
        self._apply_btn.setProperty("accent", True)
        self._apply_btn.clicked.connect(self._on_apply_clicked)
        btn_row1.addWidget(self._apply_btn)

        layout.addLayout(btn_row1)

        # Buttons row 2
        btn_row2 = QHBoxLayout()

        self._delete_btn = QPushButton("Delete")
        self._delete_btn.clicked.connect(self._on_delete_clicked)
        btn_row2.addWidget(self._delete_btn)

        self._reset_btn = QPushButton("Reset Defaults")
        self._reset_btn.clicked.connect(self._on_reset_clicked)
        btn_row2.addWidget(self._reset_btn)

        layout.addLayout(btn_row2)

        # Main widget layout
        widget_layout = QVBoxLayout(self)
        widget_layout.setContentsMargins(0, 0, 0, 0)
        widget_layout.addWidget(group)

    def _load_presets(self):
        """Load presets from file or use defaults."""
        self._presets = []

        if self._config_path and os.path.exists(self._config_path):
            try:
                with open(self._config_path, 'r') as f:
                    data = yaml.safe_load(f)
                    if data and 'presets' in data:
                        for p in data['presets']:
                            self._presets.append(Preset(
                                name=p['name'],
                                u_angle=p.get('u', 0),
                                v_angle=p.get('v', 0),
                                w_angle=p.get('w', 0),
                            ))
            except (yaml.YAMLError, OSError, KeyError) as e:
                logger.error(f"Failed to load presets: {e}")

        if not self._presets:
            self._presets = list(self.DEFAULT_PRESETS)

        self._refresh_list()

    def _save_presets(self):
        """Save presets to file."""
        if not self._config_path:
            return

        try:
            data = {
                'presets': [
                    {
                        'name': p.name,
                        'u': p.u_angle,
                        'v': p.v_angle,
                        'w': p.w_angle,
                    }
                    for p in self._presets
                ]
            }

            # Ensure directory exists
            os.makedirs(os.path.dirname(self._config_path), exist_ok=True)

            with open(self._config_path, 'w') as f:
                yaml.dump(data, f, default_flow_style=False)
        except (yaml.YAMLError, OSError) as e:
            logger.error(f"Failed to save presets: {e}")

    def _refresh_list(self):
        """Refresh the preset list widget."""
        self._list.clear()
        for preset in self._presets:
            item = QListWidgetItem(f"▸ {preset.name}")
            item.setToolTip(
                f"U: {preset.u_angle:.1f}°\n"
                f"V: {preset.v_angle:.1f}°\n"
                f"W: {preset.w_angle:.1f}°"
            )
            self._list.addItem(item)

    def set_current_positions(self, u: float, v: float, w: float):
        """Update current positions (for "Add Current" feature).

        Args:
            u, v, w: Current tendon positions in degrees
        """
        self._current_positions = {'u': u, 'v': v, 'w': w}

    def _on_add_clicked(self):
        """Handle Add Current button click."""
        name, ok = QInputDialog.getText(
            self, "Add Preset", "Preset name:",
        )

        if ok and name:
            # Check for duplicate name
            if any(p.name == name for p in self._presets):
                QMessageBox.warning(
                    self, "Duplicate Name",
                    f"A preset named '{name}' already exists."
                )
                return

            preset = Preset(
                name=name,
                u_angle=self._current_positions['u'],
                v_angle=self._current_positions['v'],
                w_angle=self._current_positions['w'],
            )
            self._presets.append(preset)
            self._refresh_list()
            self._save_presets()

    def _on_apply_clicked(self):
        """Handle Apply button click."""
        current_row = self._list.currentRow()
        if 0 <= current_row < len(self._presets):
            self.preset_selected.emit(self._presets[current_row])

    def _on_item_double_clicked(self, item: QListWidgetItem):
        """Handle double-click on preset item."""
        row = self._list.row(item)
        if 0 <= row < len(self._presets):
            self.preset_selected.emit(self._presets[row])

    def _on_delete_clicked(self):
        """Handle Delete button click."""
        current_row = self._list.currentRow()
        if 0 <= current_row < len(self._presets):
            preset = self._presets[current_row]
            reply = QMessageBox.question(
                self, "Delete Preset",
                f"Delete preset '{preset.name}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                del self._presets[current_row]
                self._refresh_list()
                self._save_presets()

    def _on_reset_clicked(self):
        """Handle Reset Defaults button click."""
        reply = QMessageBox.question(
            self, "Reset Presets",
            "Reset to default presets? This will remove all custom presets.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._presets = list(self.DEFAULT_PRESETS)
            self._refresh_list()
            self._save_presets()

    def get_preset(self, name: str) -> Optional[Preset]:
        """Get a preset by name.

        Args:
            name: Preset name

        Returns:
            Preset if found, None otherwise
        """
        for preset in self._presets:
            if preset.name == name:
                return preset
        return None
