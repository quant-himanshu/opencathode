import numpy as np
import math
import time
from typing import Generator, Dict

class NASABatterySimulator:
    def __init__(self, cell_id="B5", noise_level=0.002):
        self.cell_id = cell_id
        self.noise = noise_level
        self.cycle = 0
        self.t = 0.0
        self.rng = np.random.default_rng(seed=42 if cell_id=="B5" else 43)
        self.capacity_fade_per_cycle = 0.0018
        self.sei_growth_rate = 0.08
        self.initial_capacity = 2.0

    def _nasa_ocp_neg(self, soc):
        x = max(0.01, min(0.99, 0.1 + soc * 0.75))
        return (0.7222 + 0.1387*x + 0.029*x**0.5
                - 0.0172/x + 0.0019/x**1.5
                + 0.2808*math.exp(0.9 - 15.0*x)
                - 0.7984*math.exp(0.4465*x - 0.4108))

    def current_capacity(self):
        fade = self.capacity_fade_per_cycle * self.cycle
        return max(0.5, self.initial_capacity * (1.0 - fade))

    def stream_charge_cycle(self, C_rate=0.5, dt=1.0) -> Generator[Dict, None, None]:
        cap = self.current_capacity()
        I = C_rate * cap
        soc = 0.0
        t_cycle = 0.0
        sei_nm = 5.0 + self.sei_growth_rate * self.cycle
        R_cell = 0.05 + sei_nm * 0.0005

        while soc < 0.999 and True:
            V_ocp = self._nasa_ocp_neg(soc) + 3.7
            eta_ohmic = I * R_cell
            eta_anode = -(0.001 + 0.002 * soc)
            V = V_ocp + eta_ohmic + self.rng.normal(0, self.noise)
            V = min(4.2, V)
            if V >= 4.19:
                I = max(0.02 * cap, I * 0.98)
                if I < 0.02 * cap:
                    break
            soc = min(1.0, soc + I * dt / (cap * 3600))
            t_cycle += dt
            self.t += dt
            plating_risk = max(0.0, (-eta_anode - 0.005) / 0.010) if eta_anode < -0.005 else 0.0
            yield {
                "cell_id": self.cell_id,
                "cycle": self.cycle,
                "t": self.t,
                "t_cycle": t_cycle,
                "V": round(V, 4),
                "I": round(I, 4),
                "SOC": round(soc, 4),
                "SOH": round(1.0 - self.capacity_fade_per_cycle * self.cycle / 0.3, 4),
                "capacity_Ah": round(cap, 4),
                "sei_nm": round(sei_nm, 3),
                "eta_anode_mV": round(eta_anode * 1000, 2),
                "plating_risk": round(min(1.0, plating_risk), 3),
                "temperature_C": 25.0 + self.rng.normal(0, 0.5),
            }
        self.cycle += 1

    def stream_discharge_cycle(self, C_rate=0.5, dt=1.0) -> Generator[Dict, None, None]:
        cap = self.current_capacity()
        I = -C_rate * cap
        soc = 1.0
        t_cycle = 0.0
        sei_nm = 5.0 + self.sei_growth_rate * self.cycle
        R_cell = 0.05 + sei_nm * 0.0005
        while soc > 0.001:
            V_ocp = self._nasa_ocp_neg(soc) + 3.7
            V = V_ocp - abs(I) * R_cell + self.rng.normal(0, self.noise)
            V = max(2.5, V)
            if V <= 2.51: break
            soc = max(0.0, soc + I * dt / (cap * 3600))
            t_cycle += dt
            self.t += dt
            yield {
                "cell_id": self.cell_id, "cycle": self.cycle,
                "t": self.t, "t_cycle": t_cycle,
                "V": round(V, 4), "I": round(I, 4),
                "SOC": round(soc, 4),
                "SOH": round(1.0 - self.capacity_fade_per_cycle * self.cycle / 0.3, 4),
                "capacity_Ah": round(cap, 4),
                "sei_nm": round(sei_nm, 3),
                "eta_anode_mV": 0.0, "plating_risk": 0.0,
                "temperature_C": 25.0 + self.rng.normal(0, 0.5),
            }
        self.cycle += 1
