
import numpy as np
import math
from typing import Dict, List, Optional
from dataclasses import dataclass

F = 96485.0
R = 8.314

@dataclass
class TCOResult:
    valid: bool
    corrected_value: float
    violation_severity: float
    causal_penalty: float
    degradation_contribution: float
    message: str

class ButlerVolmerTCO:
    PLATING_THRESHOLD = -0.015
    def __init__(self, T=298.15, alpha=0.5):
        self.T = T
        self.alpha = alpha
        self.F_RT = F / (R * T)
        self.plating_events = 0
        self.cumulative_plating_charge = 0.0

    def exchange_current(self, k, c_s, c_s_max, c_e):
        cs = max(1e-6, min(c_s_max - 1e-6, c_s))
        return k * F * math.sqrt(cs * (c_s_max - cs) * max(1e-6, c_e))

    def apply(self, j, eta, k, c_s, c_s_max, c_e):
        j0 = self.exchange_current(k, c_s, c_s_max, c_e)
        j_bv = j0 * (math.exp(self.alpha * self.F_RT * eta) -
                     math.exp(-(1 - self.alpha) * self.F_RT * eta))
        dev = abs(j - j_bv) / max(j0, 1e-10)
        plating = 0.0
        if eta < self.PLATING_THRESHOLD:
            self.plating_events += 1
            plating = min(1.0, abs(eta - self.PLATING_THRESHOLD) / 0.05)
            self.cumulative_plating_charge += abs(j) * 1e-3
        return TCOResult(
            valid=(dev < 0.1 and eta >= self.PLATING_THRESHOLD),
            corrected_value=j_bv if dev > 0.1 else j,
            violation_severity=max(dev, plating),
            causal_penalty=dev * 50 + plating * 100,
            degradation_contribution=plating * 0.001,
            message=f"eta={eta*1000:.1f}mV plating={'YES' if eta < self.PLATING_THRESHOLD else 'no'}"
        )

    def get_plating_risk(self, eta):
        if eta >= 0: return 0.0
        if eta >= self.PLATING_THRESHOLD:
            return (eta / self.PLATING_THRESHOLD) ** 2
        return min(1.0, 1.0 + abs(eta - self.PLATING_THRESHOLD) / 0.05)

    def predict_plating_onset(self, eta, d_eta_dt):
        if eta <= self.PLATING_THRESHOLD: return 0.0
        if d_eta_dt >= 0: return None
        return (self.PLATING_THRESHOLD - eta) / d_eta_dt

class SEIGrowthTCO:
    E_a = 55000.0
    L_min = 5e-9
    def __init__(self, T=298.15, k_sei=1.5e-17):
        self.T = T
        self.k_sei = k_sei
        self.L_sei = self.L_min

    def apply(self, L_new, dt):
        k_eff = self.k_sei * math.exp(-self.E_a / (R * self.T))
        L_max = self.L_sei + k_eff * dt / max(1e-10, self.L_sei)
        if L_new < self.L_sei:
            corrected = self.L_sei
            sev = min(1.0, (self.L_sei - L_new) / self.L_sei)
        else:
            corrected = min(L_new, L_max * 10)
            sev = 0.0
        self.L_sei = max(self.L_min, corrected)
        return TCOResult(
            valid=(sev == 0),
            corrected_value=self.L_sei,
            violation_severity=sev,
            causal_penalty=sev * 100,
            degradation_contribution=(self.L_sei - self.L_min) * 2e6,
            message=f"SEI={self.L_sei*1e9:.2f}nm"
        )

    def get_sei_resistance(self):
        return 100e3 * self.L_sei

class ThermodynamicCausalOperatorEngine:
    def __init__(self, params, T=298.15):
        self.T = T
        self.params = params
        self.bv_tco = ButlerVolmerTCO(T=T, alpha=params.get("alpha", 0.5))
        self.sei_tco = SEIGrowthTCO(T=T, k_sei=params.get("k_sei", 1.5e-17))
        self.step_count = 0
        self.total_causal_penalty = 0.0
        self.mode_history = []
        self.current_mode = "STABLE"

    def apply_all(self, state, dt):
        eta = state.get("eta", 0.0)
        r3 = self.bv_tco.apply(
            state.get("j", 0.0), eta,
            self.params.get("k_neg", 6.48e-7),
            state.get("c_s", 15000.0),
            self.params.get("c_s_max", 30555.0),
            state.get("c_e", 1200.0)
        )
        r4 = self.sei_tco.apply(state.get("L_sei", 5e-9), dt)
        plating_risk = self.bv_tco.get_plating_risk(eta)
        if plating_risk > 0.8: mode = "PLATING"
        elif r4.degradation_contribution > 0.01: mode = "SEI_GROWTH"
        else: mode = "STABLE"
        self.current_mode = mode
        self.mode_history.append(mode)
        self.step_count += 1
        penalty = r3.causal_penalty + r4.causal_penalty
        self.total_causal_penalty += penalty
        return {
            "total_causal_penalty": penalty,
            "total_violation_severity": r3.violation_severity,
            "degradation_mode": mode,
            "plating_risk": plating_risk,
            "plating_onset_seconds": self.bv_tco.predict_plating_onset(eta, state.get("d_eta_dt", 0.0)),
            "sei_thickness_nm": self.sei_tco.L_sei * 1e9,
            "sei_resistance": self.sei_tco.get_sei_resistance(),
            "globally_consistent": r3.violation_severity < 0.1,
            "corrected_j": r3.corrected_value,
            "corrected_L_sei": r4.corrected_value,
        }

    def get_causal_diagnosis(self):
        recent = self.mode_history[-1000:]
        counts = {}
        for m in recent: counts[m] = counts.get(m, 0) + 1
        total = max(1, len(recent))
        return {
            "dominant_mode": max(counts, key=counts.get) if counts else "STABLE",
            "mode_fractions": {k: v/total for k, v in counts.items()},
            "total_steps": self.step_count,
            "sei_thickness_nm": self.sei_tco.L_sei * 1e9,
            "plating_events": self.bv_tco.plating_events,
            "plating_charge": self.bv_tco.cumulative_plating_charge,
        }

    def reset(self):
        self.step_count = 0
        self.total_causal_penalty = 0.0
        self.mode_history.clear()
        self.current_mode = "STABLE"
