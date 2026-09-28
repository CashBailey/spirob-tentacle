# SpiRob

A ROS2 package for controlling a 3-tendon soft robotic tentacle using Waveshare ST/SC serial bus servos.

## Features

- **3-Tendon Control** - Independent control of U, V, W tendons with ±2292° range
- **PyQt6 GUI** - Beautiful dark-themed control panel with real-time feedback
- **Controller Support** - Xbox/PS5 gamepad with intuitive stick mapping
- **Auto-Discovery** - Automatically detects servo bus and controllers
- **Real-Time Telemetry** - Live position graphs with pyqtgraph
- **Preset Poses** - Save and recall robot configurations
- **Safety Features** - E-stop, soft limits, temperature monitoring

## Hardware Requirements

- **Servos**: 3x Waveshare ST/SC serial bus servos (configured as IDs 1, 2, 3)
- **Interface**: USB-Serial adapter capable of 1Mbps baud rate
- **Power**: Appropriate power supply for servos (6-12V typical)
- **Optional**: Xbox One, Xbox Series, PS5, or compatible gamepad

## Installation

### Prerequisites

- ROS2 Jazzy (or compatible distribution)
- Python 3.10+

### Build the Package

```bash
# Navigate to your ROS2 workspace
cd ~/ros2_ws/src

# Clone the repository (if not already present)
# git clone <repository-url> spirob

# Install ROS dependencies
cd ~/ros2_ws
rosdep install --from-paths src --ignore-src -r -y

# Build
colcon build --packages-select spirob
source install/setup.bash
```

### Install GUI Dependencies

The GUI requires additional Python packages:

```bash
pip install PyQt6 pyqtgraph pygame pyyaml
```

### Serial Port Permissions

Add your user to the `dialout` group for serial port access:

```bash
sudo usermod -a -G dialout $USER
# Log out and back in for changes to take effect
```

## Quick Start

Launch everything with a single command:

```bash
ros2 launch spirob spirob_gui.launch.py
```

This starts the servo driver with auto-discovery and opens the GUI control panel.

## Usage

### Launch with GUI (Recommended)

```bash
ros2 launch spirob spirob_gui.launch.py
```

### Launch Driver Only

```bash
ros2 launch spirob spirob_bus.launch.py
```

### Specify Serial Port

```bash
# Use a specific port instead of auto-discovery
ros2 launch spirob spirob_bus.launch.py port:=/dev/ttyUSB0
```

### Run GUI Separately

```bash
# Terminal 1: Start driver
ros2 launch spirob spirob_bus.launch.py

# Terminal 2: Start GUI
ros2 run spirob spirob_gui
```

## Controller Mapping

Connect an Xbox or PlayStation controller for intuitive analog control:

```text
┌─────────────────────────────────────────────────────────┐
│                    CONTROLLER LAYOUT                    │
│                                                         │
│    [LB] Slow Mode      [Y/△] E-STOP      [RB] Fast Mode │
│                                                         │
│      ┌───┐                                 ┌───┐        │
│      │ ↑ │ U Tendon (+)                    │ ↑ │ W (+)  │
│    ┌─┼───┼─┐                             ┌─┼───┼─┐      │
│    │←│ L │→│ V Tendon (←/→)              │ │ R │ │      │
│    └─┼───┼─┘                             └─┼───┼─┘      │
│      │ ↓ │ U Tendon (-)                    │ ↓ │ W (-)  │
│      └───┘                                 └───┘        │
│                                                         │
│    [Back/Share] Zero All    [Start/Options] Torque      │
│                                                         │
│    [A/✕] Toggle Torque      [B/○] Reset E-Stop          │
└─────────────────────────────────────────────────────────┘
```

### Speed Modifiers

| Buttons | Speed  | Use Case         |
| ------- | ------ | ---------------- |
| None    | 90°/s  | Normal operation |
| LB held | 30°/s  | Fine positioning |
| RB held | 180°/s | Fast movement    |
| LB + RB | 360°/s | Maximum speed    |

### Button Functions

| Button   | Xbox | PlayStation | Function                   |
| -------- | ---- | ----------- | -------------------------- |
| E-Stop   | Y    | △           | Emergency stop (immediate) |
| Torque   | A    | ✕           | Toggle torque on/off       |
| Reset    | B    | ○           | Reset E-stop               |
| Zero All | Back | Share       | Zero all tendons           |

## Configuration

Configuration is stored in `config/spirob_default.yaml`:

```yaml
spirob_bus:
  ros__parameters:
    # Connection
    port: 'auto'        # 'auto' or specific like '/dev/ttyUSB0'
    baud: 1000000       # 1 Mbps for ST/SC servos

    # Servo ID mapping
    id_map:
      u: 1
      v: 2
      w: 3

    # Soft limits (degrees)
    soft_limits:
      u: { min_deg: -2292.0, max_deg: 2292.0 }
      v: { min_deg: -2292.0, max_deg: 2292.0 }
      w: { min_deg: -2292.0, max_deg: 2292.0 }

    # Spool geometry
    spool:
      core_radius_mm: 5.0    # 10mm diameter spool
      tendon_diameter_mm: 1.0
```

## ROS2 Interface

### Published Topics

| Topic                  | Type                             | Description                      |
| ---------------------- | -------------------------------- | -------------------------------- |
| `/servo/joint_states`  | `sensor_msgs/JointState`         | Current positions (radians)      |
| `/servo/diagnostics`   | `diagnostic_msgs/DiagnosticArray`| Health, temperature, errors      |
| `/servo/{u,v,w}/angle` | `std_msgs/Float32`               | Individual positions (degrees)   |

### Subscribed Topics

| Topic                        | Type               | Description                |
| ---------------------------- | ------------------ | -------------------------- |
| `/servo/{u,v,w}/target_angle`| `std_msgs/Float32` | Target position (degrees)  |
| `/servo/torque_enable`       | `std_msgs/Bool`    | Enable/disable all torque  |

### Services

| Service                    | Type                | Description                    |
| -------------------------- | ------------------- | ------------------------------ |
| `/servo/{u,v,w}/zero_here` | `std_srvs/Trigger`  | Set current position as zero   |
| `/servo/emergency_stop`    | `std_srvs/Trigger`  | Trigger E-stop                 |
| `/servo/reset_estop`       | `std_srvs/Trigger`  | Reset E-stop                   |
| `/servo/scan_bus`          | `std_srvs/Trigger`  | Scan for servos                |

### Command Examples

```bash
# Move U tendon to 90 degrees
ros2 topic pub /servo/u/target_angle std_msgs/Float32 "data: 90.0"

# Enable torque
ros2 topic pub /servo/torque_enable std_msgs/Bool "data: true"

# Zero the V tendon
ros2 service call /servo/v/zero_here std_srvs/srv/Trigger

# Trigger emergency stop
ros2 service call /servo/emergency_stop std_srvs/srv/Trigger
```

## GUI Features

### Control Panel

- **Sliders**: Drag to set target position (-2292° to +2292°)
- **Input Fields**: Type exact angle and press "Go"
- **Zero Buttons**: Calibrate each tendon independently

### Status Panel

- Connection indicators (ROS, Bus, Controller)
- Per-servo health status
- Torque enable checkbox
- Speed limit slider

### Telemetry Graph

- Real-time position history
- Color-coded: U (blue), V (green), W (orange)
- Time window: 5s, 30s, or 60s
- Pause/resume for analysis

### Presets

- Save current pose with custom name
- Double-click to apply preset
- Default presets: Home, Curl Left, Curl Right, Extend, Wrap

## Troubleshooting

### Serial Port Permission Denied

```bash
# Add user to dialout group
sudo usermod -a -G dialout $USER
# Log out and back in
```

### Servos Not Responding

1. Check servo IDs match config (default: 1, 2, 3)
2. Verify baud rate is 1Mbps
3. Check power supply to servos
4. Try manual port: `port:=/dev/ttyUSB0`

### Controller Not Detected

1. Ensure pygame is installed: `pip install pygame`
2. Check controller is connected before starting GUI
3. Try reconnecting the controller

### GUI Won't Start

```bash
# Install all GUI dependencies
pip install PyQt6 pyqtgraph pygame pyyaml

# Check for import errors
python3 -c "from spirob.gui import main; print('OK')"
```

### Auto-Discovery Fails

```bash
# List available serial ports
python3 -c "from spirob.bus import list_available_ports; print(list_available_ports())"

# Specify port manually
ros2 launch spirob spirob_bus.launch.py port:=/dev/ttyUSB0
```

## Project Structure

```text
spirob/
├── config/
│   ├── spirob_default.yaml    # Default configuration
│   └── presets_default.yaml   # Default pose presets
├── launch/
│   ├── spirob_bus.launch.py   # Driver only
│   └── spirob_gui.launch.py   # Driver + GUI
├── spirob/
│   ├── bus/                   # Serial communication
│   │   ├── bus_adapter.py     # Low-level protocol
│   │   ├── discovery.py       # Port auto-discovery
│   │   └── servo.py           # Servo abstraction
│   ├── control/               # Control layer
│   │   ├── servo_manager.py   # Multi-servo coordination
│   │   ├── safety.py          # Limits and E-stop
│   │   └── spool_geometry.py  # Tendon displacement
│   ├── gui/                   # PyQt6 GUI
│   │   ├── main_window.py     # Main application
│   │   ├── controller.py      # Gamepad handler
│   │   ├── ros_bridge.py      # ROS2 integration
│   │   └── widgets/           # UI components
│   ├── protocol/              # Servo protocol
│   │   ├── constants.py       # Commands, registers
│   │   └── packet.py          # Packet building
│   └── ros/                   # ROS2 interface
│       ├── spirob_bus_node.py # Main node
│       ├── publishers.py      # Topic publishers
│       └── services.py        # Service handlers
├── package.xml
├── setup.py
└── README.md
```

## License

MIT License
