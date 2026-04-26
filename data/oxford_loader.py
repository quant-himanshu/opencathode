import numpy as np
import math
from typing import Generator, Dict

class OxfordBatterySimulator:
    """
    Oxford Battery Degradation Dataset simulator.
    8 LiCoO2/Graphite cells, 100+ cycles each.
    Plett 2016 — University of Oxford.
    """
    def __init__(self, cell_id="Cell1", noise_level=0.003):
        self.cell_id = cell_id
        self.noise = noise_level
        self.cycle = 0
        self.t = 0.0
        self.rng = np.random.default_rng(seed=hash(cell_id) % 2**32)
        self.capacity_fade_per_cycle = 0.0015
        self.sei_growth_rate = 0.06
        self.initial_capacity = 0.74  # Ah (small pouch cells)

    def _ocp(self, soc):
        x = max(0.01, min(0.99, 0.05 + soc * 0.80))
        return (4.19829 + 0.00527*x - 1.07402*x**2
                + 1.93255*x**3 - 1.68455*x**4)

    def current_capacity(self):
        return max(0.2, self.initial_capacity * (1 - self.capacity_fade_per_cycle * self.cycle))

    def stream_charge_cycle(self, C_rate=1.0, dt=1.0) -> Generator[Dict, None, None]:
        cap = self.current_capacity()
        I = C_rate * cap
        soc = 0.0
        t_cycle = 0.0
        sei_nm = 5.0 + self.sei_growth_rate * self.cycle
        R_cell = 0.08 + sei_nm * 0.0008

        while soc < 0.999:
            V_ocp = self._ocp(soc)
            eta_ohmic = I * R_cell
            eta_anode = -(0.001 + 0.0025 * soc)
            V = V_ocp + eta_ohmic + self.rng.normal(0, self.noise)
            V = min(4.2, V)
            if V >= 4.19:
                I = max(0.02 * cap, I * 0.97)
                if I < 0.02 * cap:
                    break
            soc = min(1.0, soc + I * dt / (cap * 3600))
            t_cycle += dt
            self.t += dt
            plating_risk = max(0.0, (-eta_anode - 0.005) / 0.010) if eta_anode < -0.005 else 0.0
            yield {
                "dataset": "Oxford",
                "cell_id": self.cell_id,
                "cycle": self.cycle,
                "t": self.t,
                "t_cycle": t_cycle,
                "V": round(V, 4),
                "I": round(I, 4),
                "SOC": round(soc, 4),
                "SOH": round(max(0.0, 1.0 - self.capacity_fade_per_cycle * self.cycle / 0.3 + self.rng.normal(0, 0.008)), 4),
                "capacity_Ah": round(cap, 4),
                "sei_nm": round(sei_nm, 3),
                "eta_anode_mV": round(eta_anode * 1000, 2),
                "plating_risk": round(min(1.0, plating_risk), 3),
                "temperature_C": 25.0 + self.rng.normal(0, 0.8),
            }
        self.cycle += 1

    def stream_discharge_cycle(self, C_rate=1.0, dt=1.0) -> Generator[Dict, None, None]:
        cap = self.current_capacity()
        I = -C_rate * cap
        soc = 1.0
        t_cycle = 0.0
        sei_nm = 5.0 + self.sei_growth_rate * self.cycle
        R_cell = 0.08 + sei_nm * 0.0008
        while soc > 0.001:
            V_ocp = self._ocp(soc)
            V = V_ocp - abs(I) * R_cell + self.rng.normal(0, self.noise)
            V = max(2.7, V)
            if V <= 2.71: break
            soc = max(0.0, soc + I * dt / (cap * 3600))
            t_cycle += dt
            self.t += dt
            yield {
                "dataset": "Oxford",
                "cell_id": self.cell_id,
                "cycle": self.cycle,
                "t": self.t, "t_cycle": t_cycle,
                "V": round(V, 4), "I": round(I, 4),
                "SOC": round(soc, 4),
                "SOH": round(max(0.0, 1.0 - self.capacity_fade_per_cycle * self.cycle / 0.3 + self.rng.normal(0, 0.008)), 4),
                "capacity_Ah": round(cap, 4),
                "sei_nm": round(sei_nm, 3),
                "eta_anode_mV": 0.0, "plating_risk": 0.0,
                "temperature_C": 25.0 + self.rng.normal(0, 0.8),
            }
        self.cycle += 1
