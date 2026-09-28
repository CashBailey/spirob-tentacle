# High-Level Design Specification

**System:** SpiRob-Inspired 3-Tendon Soft Robotic Tentacle using Serial Bus Servos
**Version:** 1.1
**Date:** 2026-02-04
**Owner:** Cash (Systems and Controls)
**Stakeholders:** Controls, Mechatronics, Embedded, ROS Integration, QA

---

## 0) SpiRob Design Context

This tentacle is based on the **SpiRob design concept**: a spiral-shaped, cable-actuated soft robot that achieves versatile grasping and manipulation by **curling and uncurling** along its body and **wrapping** around objects. The core idea is that a spiral-shaped morphology paired with **2 or 3 cable actuation** enables adaptive reaching and grasping behaviors with minimal sensing and minimal planning complexity.

### How SpiRob maps to this project

* **Mechanical morphology:** The tentacle body follows the SpiRob style: a spiral-like tapered body intended to curl/uncurl and wrap during actuation.
* **Actuation model:** SpiRob uses cables (tendons) to generate curling and controlled deformation. This project uses **three tendons (U, V, W)** spaced around the body, aligned with the SpiRob 3-cable concept for 3D deformation (bending plus torsion).
* **Control philosophy:** Instead of implementing a custom low-level PID loop, the system issues high-level position/speed/limit commands and relies on actuator internal control for regulation. The higher-level behaviors still align with SpiRob operation: staged curling/uncurling and wrapping behaviors driven by tendon commands.

---

## 1) Executive Summary

This system actuates a **soft robotic tentacle** using the **SpiRob-inspired spiral geometry** and **three tendons** (U, V, W). Each tendon is driven by a **serial-bus servo** through a **serial bus servo driver board** that provides both power distribution and command/feedback on a single bus.

The host computer (Linux) runs **ROS 2 (Jazzy)** and a driver node that connects over **USB** to the servo driver board. The node exposes ROS topics/services/actions for commanding tendon motion (position/speed/torque limits), receiving joint states, logging telemetry, and handling faults. Load variation from tendon wrap is handled at a **high level** through speed/torque limits, pre-tension, and adaptive command scheduling, while each servo’s internal controller closes the loop.

---

## 2) Scope

### In scope

* SpiRob-inspired 3-tendon actuation (U/V/W) using serial-bus servos with two-way feedback.
* ROS 2 node implementing high-level command/telemetry, fault handling, and logging.
* Bus discovery, servo ID assignment/mapping (U/V/W).
* Commissioning, zeroing, soft-limits per tendon.
* Load compensation strategies that do not require custom low-level PID.

### Out of scope

* Designing a custom motor controller, custom CRC framing, or a low-level PID loop on the host (control is internal to the bus servos).
* Firmware changes inside the bus servos or driver board.
* Non-bus actuator types.

---

## 3) Hardware Overview

### 3.1 Inventory (Parts List)

| Qty | Device                                                                                                                              |
| --: | ----------------------------------------------------------------------------------------------------------------------------------- |
|   1 | Serial Bus Servo Driver Board - Control Up to 253 ST/SC Series Servos with Supplied Power                                           |
|   3 | Waveshare 30KG High Torque Serial Bus Servo Motor, 360 Programmable Magnetic Encoder, Two-Way Feedback, Servo/Motor Mode Switchable |

### 3.2 Electrical

* Driver board supplies bus power per its rating; servos are daisy-chained on the bus (signal + power).
* Host PC ↔ USB ↔ Driver board ↔ Bus ↔ Servos U/V/W.
* Common ground; bus termination and wiring per board requirements.

### 3.3 Mechanical (SpiRob-informed)

* Each servo drives a spool connected to a tendon.
* Spool geometry (core radius, tendon diameter, wrap width) is documented to estimate **effective radius vs. layer count** for load-aware command adaptation.
* Tendon routing aligns with the SpiRob 3-cable concept: three tendons distributed around the body to produce combined bending and torsion behaviors.

---

## 4) System Context and Data Flow

### Actors

* Operator / higher-level controller (ROS tools, GUI, or planning node)
* ROS 2 Driver Node (“spirob_bus”)
* Driver board (USB device)
* Three servos (U/V/W)

### Flows

1. Operator commands a target (angle/length or speed) for U/V/W via ROS.
2. Driver node translates to bus servo commands (set position/speed/torque enable, etc.).
3. Servos execute internally and stream back feedback (position, speed, voltage, temperature, status).
4. Driver node publishes `/joint_states` and diagnostics; logs telemetry; handles faults.

---

## 5) Functional Requirements

### F-1 Commanding

* Absolute/relative position commands per tendon.
* Speed setpoints per tendon (when needed).
* Torque/compliance: torque enable/disable, torque limit if supported.
* Zero/offset: set current spool angle as zero.
* Mode switch: servo vs motor mode (if provided by the servo).

### F-2 Feedback

* Position (deg), velocity (deg/s or RPM), bus voltage, temperature, status flags (over-temp, overload, over-current, torque limiting, comm errors).
* Heartbeat/telemetry rate ≥ 50 Hz.

### F-3 Discovery and Addressing

* Enumerate bus devices on connect; map IDs to labels U/V/W; persist mapping.
* Reassign IDs if necessary during commissioning.

### F-4 Limits and Safety

* Per-tendon soft-limits in spool rotation or tendon length.
* Configurable speed and torque ceilings per move.
* Emergency stop (immediate torque disable for all).

### F-5 Calibration

* Zeroing procedure per tendon.
* Optional auto-sweep to confirm encoder zero and direction.
* Spool geometry entry: `core_radius_mm`, `tendon_diameter_mm`, `wrap_width_mm`, `usable_layers`.

### F-6 Logging and Replay

* CSV log of timestamped position/command/error plus servo status.
* ROS bag option for integration tests.

---

## 6) Non-Functional Requirements

### Performance

* End-to-end command latency (host to measured effect): ≤ 40 ms.
* Telemetry throughput: ≥ 50 Hz sustained for 3 servos.
* Startup connect time: ≤ 2 s after USB plug-in.

### Reliability

* Automatic reconnect on USB drop.
* Fault-tolerant to single servo loss; publish degraded state.

### Maintainability

* Clear separation of bus adapter vs ROS interfaces.
* Configuration via ROS parameters / YAML.

### Safety

* Torque cut on any FAIL flag from servo or on lost comm heartbeat > 200 ms.
* Temperature and voltage guardrails from servo status.

---

## 7) Software Architecture

### Layers

1. **ROS Interface Layer**

   * Topics/services/actions, parameters, diagnostics, logging.

2. **Control Orchestration Layer**

   * Command scheduling, move profiles, load-aware adjustments (Section 10).
   * Soft-limits, rate limiting, watchdogs, stuck detection.

3. **Bus Adapter Layer**

   * USB serial to driver board; bus protocol implementation (vendor command set).
   * Device scan, read/write registers, ID assignment, retry/timeout handling.

**Key Node:** `spirob_bus` (rclpy recommended for fast iteration).

---

## 8) ROS 2 Interfaces

### Subscriptions

* `/servo/u/target_angle` (`std_msgs/Float32`)
* `/servo/v/target_angle` (`std_msgs/Float32`)
* `/servo/w/target_angle` (`std_msgs/Float32`)
* Optional: `/servo/*/target_speed` (`std_msgs/Float32`)
* `/servo/torque_enable` (`std_msgs/Bool`) for all or per-servo variants.

### Publications

* `/servo/joint_states` (`sensor_msgs/JointState`) names: `joint_u`, `joint_v`, `joint_w`; `position[]` in radians, `velocity[]` optional.
* `/servo/diagnostics` (`diagnostic_msgs/DiagnosticArray`) status per servo plus bus health.
* Convenience: `/servo/*/angle_deg` (`std_msgs/Float32`).

### Services

* `/servo/*/zero_here` (`std_srvs/Trigger`)
* `/servo/*/set_torque_limit` (custom srv: percent or mA if supported)
* `/servo/*/set_id` (commissioning only)
* `/servo/save_params` (`std_srvs/Trigger`) if supported.

### Optional Actions

* `/servo/move_to` (trajectory or simple goal with tolerance and timeout).

### Parameters (core)

* `port`, `baud` (default per board manual), `id_map: {u: 1, v: 2, w: 3}`
* `telemetry_rate_hz` (50-100)
* Soft-limits per tendon (deg or length), `speed_limit`, `torque_limit`
* Spool geometry: `core_radius_mm`, `tendon_diameter_mm`, `wrap_width_mm`, `usable_layers`

---

## 9) Commissioning and Calibration

### C-1 Assign IDs

* Connect one servo at a time or isolate using power jumpers.
* Use bus scan to find device, set ID to 1/2/3 for U/V/W, then save.

### C-2 Zeroing

* Manually set a mechanical reference mark; command Zero Here to store as offset in node or servo (depending on capability).

### C-3 Direction Check

* Command +360° test move. Confirm tendon pulls in intended direction for each of U/V/W; flip sign in config if not.

### C-4 Soft-limits

* Measure end-stops/limits. Enter conservative soft-limits, test, then widen as needed.

### C-5 Spool Geometry

* Enter spool/tendon dimensions. Node computes effective radius vs wrap layers for planning (Section 10).

---

## 10) Load Compensation Strategy (High Level)

Even with internal servo control, tendon load rises as wraps accumulate. The driver node applies command-level compensation:

### LC-1 Effective Radius Estimation

Track wraps/layers to estimate `r_eff = r_core + layer_count * tendon_diameter` (adjust for multi-track winding if used). This allows command scheduling that anticipates increased required torque at larger `r_eff`.

### LC-2 Progress-based Adaptation

During a move:

* If |error| is steady and progress < ε for Δt, raise speed and/or torque limit one step (up to configured cap).
* Once progress resumes, roll back to nominal.

### LC-3 Pre-tension and Anti-slack

Before reel-in, apply a brief pre-tension pulse (small torque/position nudge) to remove slack, then execute the main move.

### LC-4 Thermal and Power Guardrails

If servo reports high temperature or low bus voltage, cap torque and slow commanded speed to avoid trips.

### LC-5 Operator Overrides

Expose an “assertive mode” preset that bumps speed and torque ceilings for moves known to fight heavy wrap.

---

## 11) Fault Handling

### Detection

* Bus timeouts and protocol errors at adapter layer.
* Servo flags: over-temp, over-current, overload, angle limit, voltage fault.

### Response

* Per-tendon fault: torque disab
le that tendon, publish error, keep others alive when safe.
* Global fault (power brownout, repeated bus failure): all-stop and notify.

### Recovery

* Automatic retry with back-off; reconnect USB; re-enumerate devices; restore last known limits and offsets.

---

## 12) Telemetry, Logging, and Tools

* Publish `/servo/joint_states` and `/servo/diagnostics` at configured rate.
* Optional CSV logger: time, command, measured angle, error, `r_eff`, speed/torque limits, status flags.
* GUI tuner to visualize angle vs target, issue test moves, adjust speed/torque ceilings, and run commissioning routines.

---

## 13) Performance and Acceptance Criteria

* Connect and enumerate within ≤ 2 s after node launch.
* Command-to-motion latency ≤ 40 ms.
* Telemetry rate ≥ 50 Hz, no backlog.
* Achieve commanded repeatability ≤ 0.5° at the spool in low-load segments; under high wrap, maintain no stall with LC adaptations enabled.
* Emergency stop reacts ≤ 50 ms from trigger to torque-off.

---

## 14) Security and Safety

* USB device filtering by VID/PID or `/dev/serial/by-id` path.
* Safe defaults: torque disabled at startup until commissioning completes; soft-limits enforced from config.
* Operator confirmation required for ID reassignment and save-to-NVM.

---

## 15) Risks and Mitigations

| Risk                                          | Impact                       | Mitigation                                                              |
| --------------------------------------------- | ---------------------------- | ----------------------------------------------------------------------- |
| Bus power undersized for simultaneous reel-in | Brownouts, resets            | Size PSU with margin; stagger high-load moves; monitor voltage          |
| ID conflicts on the bus                       | Lost devices, unsafe mapping | Commissioning tool isolates one servo during assignment; persist ID map |
| Thermal throttling under heavy wrap           | Slow or stalled motion       | LC-2 adaptation; temperature guardrails; cooldown strategy              |
| Model error in effective radius               | Over- or under-compensation  | Empirical calibration; learn a correction table vs spool turns          |
| USB disconnects                               | Loss of control              | Auto-reconnect, watchdog; E-stop on heartbeat loss                      |

---

## 16) Implementation Plan (Milestones)

1. Bus Adapter: open/close, read/write, scan, read status, set pos/speed/torque, set ID, save.
2. ROS Node: topics/services, parameters, diagnostics, logging.
3. Commissioning Tool/GUI: ID assignment, zero, direction test, soft-limits.
4. Load Compensation: `r_eff` model, progress-based adaptation, presets.
5. QA and Validation: acceptance tests, thermal/power tests, long-run soak.

---

## 17) Handover Artifacts

* Source tree with `spirob_bus` node and configuration.
* YAML configs for lab rig and field rig.
* Commissioning checklist (IDs, zeroing, limits).
* Test scripts for step moves (+/-5°, +/-360°, +/-720°) and heavy-wrap trials.
* Logs demonstrating acceptance criteria.

---

## 18) Glossary

* **SpiRob:** Spiral-shaped, cable-driven soft robot concept used as the mechanical and behavioral inspiration for this project.
* **Tendon:** Cable that bends the soft body when reeled.
* **Wrap:** Layers of tendon on spool; increases effective radius and load.
* **r_eff:** Effective spool radius including wraps.
* **Soft-limit:** Software-enforced motion boundary.
* **LC:** Load Compensation (high-level scheduling and limits).

---

## 19) Notes and Assumptions

* The driver board’s vendor protocol is used as-is; the adapter layer isolates vendor specifics.
* Servo telemetry includes at least position and status flags; torque/current and temperature used when available.
* ID range supports up to 253 devices; only 3 used here but the bus scales.

---

## 20) Future Extensions

* Multi-segment tentacle with >3 tendons; same bus and node scale with the ID map.
* Learned feed-forward table vs turns for tighter load compensation.
* Coordinated 3-tendon kinematics layer (map x-y-z tip commands to U/V/W spool moves).
* On-board SBC (Raspberry Pi class) as the host to remove the tether.
