"""GUI widgets for SpiRob control panel."""

from spirob.gui.widgets.tendon_control import TendonControlWidget
from spirob.gui.widgets.status_panel import StatusPanel
from spirob.gui.widgets.estop_button import EStopButton
from spirob.gui.widgets.controller_panel import ControllerPanel
from spirob.gui.widgets.telemetry_graph import TelemetryGraph
from spirob.gui.widgets.preset_panel import PresetPanel

__all__ = [
    'TendonControlWidget',
    'StatusPanel',
    'EStopButton',
    'ControllerPanel',
    'TelemetryGraph',
    'PresetPanel',
]
