import numpy as np
import math
from typing import Generator, Dict

class CALCEBatterySimulator:
    """
    CALCE Battery Research Group dataset simulator.
    University of Maryland — LiCoO2 prismatic cells.
    Multiple C-rates, temperatures, and cycling profiles.
    """
    def __init__(self, cell_id="CS2_35", chemistry="LCO", noise_level=0.002):
        self.cell_id = cell_id
        self.chemistry = chemistry
        self.noise = noise_level
        self.cycle = 0
        self.t = 0.0
        self.rng = np.random.default_rng(seed=hash(cell_id) % 2**32)
        # LCO degrades faster than NMC
        self.capacity_fade_per_cycle = 0.0025
        self.sei_growth_rate = 0.12
        self.initial_capacity = 1.1  # Ah

    def _ocp_lco(self, soc):
        """LiCoO2 OCP curve."""
        x = max(0.01, min(0.99, 0.45 + soc * 0.45))
        return (4.188 - 0.452*x - 0.895*x**2
                + 2.055*x**3 - 1.476*x**4
                - 0.015*math.exp(-10*(x-0.55)**2))

    def current_capacity(self):
        return max(0.3, self.initial_capacity * (1 - self.capacity_fade_per_cycle * self.cycle))

    def stream_charge_cycle(self, C_rate=0.5, dt=1.0) -> Generator[Dict, None, None]:
        cap = self.current_capacity()
        I = C_rate * cap
        soc = 0.0
        t_cycle = 0.0
        sei_nm = 5.0 + self.sei_growth_rate * self.cycle
        R_cell = 0.06 + sei_nm * 0.0006
        # LCO has tighter voltage window
        V_max = 4.2

        while soc < 0.999:
            V_ocp = self._ocp_lco(soc)
            eta_ohmic = I * R_cell
            # LCO anode kinetics slightly different
            eta_anode = -(0.0015 + 0.002 * soc)
            V = V_ocp + eta_ohmic + self.rng.normal(0, self.noise)
            V = min(V_max, V)
            if V >= V_max - 0.01:
                I = max(0.02 * cap, I * 0.97)
                if I < 0.02 * cap:
                    break
            soc = min(1.0, soc + I * dt / (cap * 3600))
            t_cycle += dt
            self.t += dt
            plating_risk = max(0.0, (-eta_anode - 0.005) / 0.010) if eta_anode < -0.005 else 0.0
            yield {
                "dataset": "CALCE",
                "cell_id": self.cell_id,
                "cycle": self.cycle,
                "t": self.t, "t_cycle": t_cycle,
                "V": round(V, 4), "I": round(I, 4),
                "SOC": round(soc, 4),
                "SOH": round(max(0.0, 1.0 - self.capacity_fade_per_cycle * self.cycle / 0.3 + self.rng.normal(0, 0.010)), 4),
                "capacity_Ah": round(cap, 4),
                "sei_nm": round(sei_nm, 3),
                "eta_anode_mV": round(eta_anode * 1000, 2),
                "plating_risk": round(min(1.0, plating_risk), 3),
                "temperature_C": 25.0 + self.rng.normal(0, 0.5),
                "chemistry": self.chemistry,
            }
        self.cycle += 1

    def stream_discharge_cycle(self, C_rate=0.5, dt=1.0) -> Generator[Dict, None, None]:
        cap = self.current_capacity()
        I = -C_rate * cap
        soc = 1.0
        t_cycle = 0.0
        sei_nm = 5.0 + self.sei_growth_rate * self.cycle
        R_cell = 0.06 + sei_nm * 0.0006
        while soc > 0.001:
            V_ocp = self._ocp_lco(soc)
            V = V_ocp - abs(I) * R_cell + self.rng.normal(0, self.noise)
            V = max(2.5, V)
            if V <= 2.51: break
            soc = max(0.0, soc + I * dt / (cap * 3600))
            t_cycle += dt
            self.t += dt
            yield {
                "dataset": "CALCE",
                "cell_id": self.cell_id,
                "cycle": self.cycle,
                "t": self.t, "t_cycle": t_cycle,
                "V": round(V, 4), "I": round(I, 4),
                "SOC": round(soc, 4),
                "SOH": round(max(0.0, 1.0 - self.capacity_fade_per_cycle * self.cycle / 0.3 + self.rng.normal(0, 0.010)), 4),
                "capacity_Ah": round(cap, 4),
                "sei_nm": round(sei_nm, 3),
                "eta_anode_mV": 0.0, "plating_risk": 0.0,
                "temperature_C": 25.0 + self.rng.normal(0, 0.5),
                "chemistry": self.chemistry,
            }
        self.cycle += 1
