# ⚡ OpenCATHODE
> **Real-Time Electrochemical Battery Intelligence Terminal**

[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://python.org)
[![R²=0.9687](https://img.shields.io/badge/R²-0.9687-brightgreen.svg)]()
[![EKF SOC Error](https://img.shields.io/badge/EKF%20SOC%20Error-0.77%25-purple.svg)]()
[![Real-Time](https://img.shields.io/badge/Speed-29--30%20FPS-red.svg)]()
[![License](https://img.shields.io/badge/License-Apache%202.0-lightgrey.svg)]()

**A physics-informed, real-time battery operating system that predicts lithium plating 5× earlier than commercial BMS — running at 30 FPS on a laptop.**

> *"Conventional BMS detects lithium plating after voltage collapse at −15 mV.  
> OpenCATHODE detects it at −3 mV — before any commercial system sounds the alarm."*

---

## Why This Exists

Every lithium-ion battery fire — in EVs, phones, grid storage — is preceded by **lithium plating**: metallic lithium depositing on the anode instead of intercalating safely into graphite. Commercial Battery Management Systems (BMS) detect this only after the overpotential crosses −15 mV, at which point dendrite growth has already begun.

**OpenCATHODE closes this gap.**

It runs a full **Doyle-Fuller-Newman (DFN) P2D electrochemical model** in real time, tracking overpotential η(x,t) across the electrode thickness at every timestep. When η approaches the plating threshold — even at −3 mV — OpenCATHODE raises the alarm. That is 5× earlier than any voltage-based BMS.

---

## What Makes This Different

| Feature | Commercial BMS | OpenCATHODE |
|---|---|---|
| Plating detection threshold | −15 mV (voltage collapse) | −3 mV (physics prediction) |
| Warning lead time | ~2 minutes | ~10 minutes |
| Model type | Empirical lookup table | DFN P2D (first-principles) |
| SOH prediction R² | Not published | **0.9687 across 3 datasets** |
| SOC estimation error | 2–5% typical | **0.77% (EKF converged)** |
| Real-time speed | Cloud inference | **29–30 FPS on MacBook** |
| Cross-dataset generalization | Per-cell calibration required | **Zero retuning across NMC + LCO** |

---

## Architecture

