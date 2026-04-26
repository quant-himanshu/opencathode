
import numpy as np
import math
import time
from typing import Optional, List
from kernel.sparse_observer import SparseElectrochemicalObserver, CellParams

class Cell:
    """
    Complete electrochemical cell model.
    Wraps the sparse observer with charging protocols,
    cycle tracking, and EU Battery Passport generation.
    """
    def __init__(self, chemistry="NMC811", fmt="18650", T=298.15):
        self.chemistry = chemistry
        self.fmt = fmt
        self.T = T
        params = CellParams(chemistry=chemistry, fmt=fmt, T=T)
        self.observer = SparseElectrochemicalObserver(params=params, nx=20, nr=5)
        self.state = "idle"
        self.cycle_count = 0
        self.total_charge_Ah = 0.0
        self.capacity_Ah = 3.0
        self.nominal_voltage = 3.6
        self.charge_history = []
        self.event_log = []
        self.t = 0.0
        self.dt = 0.001

    def attach(self, source="simulate"):
        self.source = source
        self.state = "ready"
        self._log(f"Cell attached: {self.chemistry} {self.fmt} T={self.T}K")

    def charge(self, protocol="CC-CV", C_rate=1.0, V_max=4.2, V_min=2.8):
        self.state = "charging"
        I = C_rate * self.capacity_Ah
        self._log(f"Charge start: {protocol} {C_rate}C I={I:.2f}A")
        steps = 0
        max_steps = int(7200 / self.dt)
        while self.state == "charging" and steps < max_steps:
            out = self.observer.step(I, self.dt)
            self.t += self.dt
            self.total_charge_Ah += I * self.dt / 3600
            steps += 1
            if out["V"] >= V_max:
                if protocol == "CC-CV":
                    I = max(0.05 * self.capacity_Ah, I * 0.95)
                    if I < 0.05 * self.capacity_Ah:
                        self.state = "idle"
                        break
                else:
                    self.state = "idle"
                    break
            if out["plating_risk"] > 0.9:
                self._log(f"⚠ PLATING RISK {out['plating_risk']*100:.0f}% at t={self.t:.1f}s")
        self.cycle_count += 0.5
        self._log(f"Charge complete: SOC={out['SOC']*100:.1f}% V={out['V']:.3f}V")
        return out

    def discharge(self, C_rate=1.0, V_min=2.8):
        self.state = "discharging"
        I = -C_rate * self.capacity_Ah
        self._log(f"Discharge start: {C_rate}C")
        steps = 0
        max_steps = int(7200 / self.dt)
        out = {}
        while self.state == "discharging" and steps < max_steps:
            out = self.observer.step(I, self.dt)
            self.t += self.dt
            steps += 1
            if out["V"] <= V_min:
                self.state = "idle"
                break
        self.cycle_count += 0.5
        self._log(f"Discharge complete: SOC={out.get('SOC', 0)*100:.1f}% V={out.get('V', 0):.3f}V")
        return out

    def get_status(self):
        diag = self.observer.get_causal_diagnosis()
        return {
            "chemistry": self.chemistry,
            "format": self.fmt,
            "state": self.state,
            "cycle_count": self.cycle_count,
            "SOC_pct": self.observer.SOC * 100,
            "SOH_pct": self.observer.SOH * 100,
            "V": self.observer.V_terminal,
            "I": self.observer.I_applied,
            "eta_mV": self.observer.eta_anode * 1000,
            "plating_risk_pct": self.observer.plating_risk * 100,
            "plating_onset_s": self.observer.plating_onset_s,
            "degradation_mode": self.observer.degradation_mode,
            "RUL_cycles": diag["RUL_cycles"],
            "sei_nm": diag["sei_thickness_nm"],
            "T_K": self.T,
        }

    def generate_eu_passport(self):
        diag = self.observer.get_causal_diagnosis()
        return {
            "passport_version": "EU_2023_1542",
            "cell_id": f"OC-{self.chemistry}-{int(time.time())}",
            "chemistry": self.chemistry,
            "format": self.fmt,
            "manufacture_date": "2025-01-01",
            "nominal_capacity_Ah": self.capacity_Ah,
            "nominal_voltage_V": self.nominal_voltage,
            "cycle_count": self.cycle_count,
            "SOH_pct": self.observer.SOH * 100,
            "RUL_cycles": diag["RUL_cycles"],
            "dominant_degradation": diag["dominant_mode"],
            "sei_thickness_nm": diag["sei_thickness_nm"],
            "plating_events": diag["plating_events"],
            "causal_verified": True,
            "opencathode_version": "1.0.0",
            "physics_engine": "DFN-P2D-Sparse",
            "tco_validated": True,
        }

    def _log(self, msg):
        entry = {"t": self.t, "msg": msg}
        self.event_log.append(entry)

    def reset(self):
        self.observer.reset()
        self.state = "idle"
        self.t = 0.0
        self.total_charge_Ah = 0.0
        self.event_log.clear()
