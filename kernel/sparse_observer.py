
import numpy as np
import math
import time
from typing import Dict, Set, Tuple, List, Optional
from dataclasses import dataclass
from kernel.tco import ThermodynamicCausalOperatorEngine

F_CONST = 96485.0
R_CONST = 8.314

@dataclass
class NodeState:
    x: int = 0
    r: int = 0
    region: str = "neg"
    c_s: float = 15000.0
    c_e: float = 1200.0
    phi_s: float = 0.0
    phi_e: float = 0.0
    j: float = 0.0
    eta: float = 0.0
    U: float = 0.12
    L_sei: float = 5e-9

@dataclass
class CellParams:
    chemistry: str = "NMC811"
    fmt: str = "18650"
    L_neg: float = 75e-6
    L_sep: float = 25e-6
    L_pos: float = 70e-6
    R_neg: float = 10e-6
    R_pos: float = 5e-6
    D_s_neg: float = 3.9e-14
    D_s_pos: float = 1.0e-14
    D_e: float = 7.5e-11
    kappa: float = 0.8
    k_neg: float = 6.48e-7
    k_pos: float = 3.42e-6
    alpha: float = 0.5
    c_s_max_neg: float = 30555.0
    c_s_max_pos: float = 51555.0
    c_e_init: float = 1200.0
    x_neg_0: float = 0.8
    x_pos_0: float = 0.45
    eps_neg: float = 0.3
    eps_sep: float = 0.4
    eps_pos: float = 0.3
    a_neg: float = 1.5e5
    a_pos: float = 1.5e5
    k_sei: float = 1.5e-17
    rho_sei: float = 100e3
    N_Li_initial: float = 1.0
    T: float = 298.15

    def ocp_neg(self, x):
        x = max(0.001, min(0.999, x))
        return (0.7222 + 0.1387*x + 0.029*x**0.5
                - 0.0172/x + 0.0019/x**1.5
                + 0.2808*math.exp(0.9 - 15.0*x)
                - 0.7984*math.exp(0.4465*x - 0.4108))

    def ocp_pos(self, x):
        x = max(0.001, min(0.999, x))
        return (4.3452 - 1.6518*x + 1.6225*x**2
                - 2.0843*x**3 + 3.5146*x**4
                - 2.2166*x**5
                - 0.5623*math.exp(109.451*x - 100.006))

class SparseElectrochemicalObserver:
    PLATING_ETA = -0.015
    VOLATILITY_EPS = 1e-4

    def __init__(self, params=None, nx=20, nr=5):
        self.p = params or CellParams()
        self.nx = nx
        self.nr = nr
        self.grid: Dict[Tuple, NodeState] = {}
        self.active: Set[Tuple] = set()
        self.damage: Set[Tuple] = set()
        self._init_grid()
        self.prev_c_s: Dict[Tuple, float] = {}
        self.prev_c_e: Dict[Tuple, float] = {}
        self.V_terminal = 3.6
        self.I_applied = 0.0
        self.SOC = 0.67
        self.SOH = 1.00
        self.eta_anode = 0.0
        self.d_eta_dt = 0.0
        self.plating_risk = 0.0
        self.plating_onset_s = None
        self.degradation_mode = "STABLE"
        tco_params = {
            "alpha": self.p.alpha,
            "k_sei": self.p.k_sei,
            "k_neg": self.p.k_neg,
            "c_s_max": self.p.c_s_max_neg,
            "U_ref": 0.12,
            "N_Li_initial": self.p.N_Li_initial,
        }
        self.tco = ThermodynamicCausalOperatorEngine(tco_params, T=self.p.T)
        self.step_count = 0
        self.sparse_fraction = 0.0
        self.t_elapsed = 0.0
        self.HIST = 10000
        self.hist_V = np.zeros(self.HIST)
        self.hist_I = np.zeros(self.HIST)
        self.hist_SOC = np.zeros(self.HIST)
        self.hist_eta = np.zeros(self.HIST)
        self.hist_sei = np.zeros(self.HIST)
        self.hist_t = np.zeros(self.HIST)
        self._hidx = 0

    def _init_grid(self):
        for region, c_max, x0 in [
            ("neg", self.p.c_s_max_neg, self.p.x_neg_0),
            ("pos", self.p.c_s_max_pos, self.p.x_pos_0),
        ]:
            for xi in range(self.nx):
                for ri in range(self.nr):
                    r_norm = ri / max(1, self.nr - 1)
                    c_s = x0 * c_max * (1.0 - 0.02 * r_norm**2)
                    key = (xi, ri, region)
                    self.grid[key] = NodeState(
                        x=xi, r=ri, region=region,
                        c_s=c_s, c_e=self.p.c_e_init,
                        U=(self.p.ocp_neg(x0) if region == "neg" else self.p.ocp_pos(x0))
                    )
                    self.active.add(key)

    def _detect_volatile_nodes(self):
        volatile = set()
        for key, node in self.grid.items():
            if node.r == 0 and abs(self.I_applied) > 0.01:
                volatile.add(key)
                continue
            prev_cs = self.prev_c_s.get(key, node.c_s)
            if abs(node.c_s - prev_cs) > self.VOLATILITY_EPS * self.p.c_s_max_neg:
                volatile.add(key)
                volatile.update(self._neighbours(key))
        return volatile

    def _neighbours(self, key):
        xi, ri, region = key
        nbrs = []
        if ri > 0: nbrs.append((xi, ri-1, region))
        if ri < self.nr-1: nbrs.append((xi, ri+1, region))
        if xi > 0: nbrs.append((xi-1, ri, region))
        if xi < self.nx-1: nbrs.append((xi+1, ri, region))
        return nbrs

    def _solve_solid_diffusion(self, key, dt):
        node = self.grid[key]
        region = node.region
        D_s = self.p.D_s_neg if region == "neg" else self.p.D_s_pos
        R_p = self.p.R_neg if region == "neg" else self.p.R_pos
        dr = R_p / max(1, self.nr - 1)
        ri = node.r
        r = ri * dr
        c_inner = self.grid.get((node.x, ri-1, region), NodeState(c_s=node.c_s)).c_s if ri > 0 else node.c_s
        c_outer = self.grid.get((node.x, ri+1, region), NodeState(c_s=node.c_s)).c_s if ri < self.nr-1 else node.c_s
        if r > 1e-10:
            laplacian = (D_s / r**2) * ((r+dr)**2*(c_outer-node.c_s)/dr - r**2*(node.c_s-c_inner)/dr) / dr
        else:
            laplacian = 6.0 * D_s * (c_outer - node.c_s) / dr**2
        if ri == self.nr - 1:
            j_flux = node.j * R_p / (3.0 * D_s) if D_s > 0 else 0.0
            laplacian -= j_flux / dr
        cs_max = self.p.c_s_max_neg if region == "neg" else self.p.c_s_max_pos
        node.c_s = max(0.0, min(cs_max, node.c_s + laplacian * dt))
        if abs(laplacian * dt) > self.VOLATILITY_EPS:
            self.damage.add(key)

    def _solve_electrolyte(self, dt):
        for region, eps in [("neg", self.p.eps_neg), ("pos", self.p.eps_pos)]:
            D_eff = self.p.D_e * eps**1.5
            L = self.p.L_neg if region == "neg" else self.p.L_pos
            dx = L / self.nx
            c_e = np.array([self.grid.get((xi, 0, region), NodeState()).c_e for xi in range(self.nx)])
            j_avg = np.mean([self.grid.get((xi, self.nr-1, region), NodeState()).j for xi in range(self.nx)])
            laplacian = np.gradient(np.gradient(c_e, dx), dx)
            sign = 1.0 if region == "neg" else -1.0
            c_e_new = np.clip(c_e + dt * (D_eff * laplacian + sign * self.p.a_neg * j_avg / F_CONST), 10.0, 4000.0)
            for xi in range(self.nx):
                for ri in range(self.nr):
                    key = (xi, ri, region)
                    if key in self.grid:
                        self.grid[key].c_e = float(c_e_new[xi])

    def _solve_reaction(self, key, I_applied):
        node = self.grid[key]
        if node.r != self.nr - 1: return
        region = node.region
        k = self.p.k_neg if region == "neg" else self.p.k_pos
        cs_max = self.p.c_s_max_neg if region == "neg" else self.p.c_s_max_pos
        x = max(1e-6, min(1-1e-6, node.c_s / cs_max))
        U = self.p.ocp_neg(x) if region == "neg" else self.p.ocp_pos(x)
        node.U = U
        c_e_safe = max(1.0, node.c_e)
        cs_safe = max(1.0, min(cs_max - 1.0, node.c_s))
        j0 = k * F_CONST * math.sqrt(cs_safe * (cs_max - cs_safe) * c_e_safe)
        sign = -1.0 if region == "neg" else 1.0
        eta_approx = sign * (I_applied / max(1e-10, j0)) * 0.025
        node.eta = eta_approx
        alpha = self.p.alpha
        F_RT = F_CONST / (R_CONST * self.p.T)
        node.j = j0 * (math.exp(alpha * F_RT * eta_approx) - math.exp(-(1-alpha) * F_RT * eta_approx))
        if region == "neg" and eta_approx < -0.005:
            k_sei_eff = self.p.k_sei * math.exp(-0.4 * F_CONST * abs(eta_approx) / (R_CONST * self.p.T))
            dL = k_sei_eff * c_e_safe**0.5 * self.p.rho_sei / (2.0 * F_CONST) * 1e-3
            node.L_sei = max(5e-9, node.L_sei + dL)

    def _compute_terminal_voltage(self):
        def avg_U(region):
            vals = [self.grid[(xi, self.nr-1, region)].U for xi in range(self.nx) if (xi, self.nr-1, region) in self.grid]
            return np.mean(vals) if vals else (0.12 if region == "neg" else 3.9)
        def avg_eta(region):
            vals = [self.grid[(xi, self.nr-1, region)].eta for xi in range(self.nx) if (xi, self.nr-1, region) in self.grid]
            return np.mean(vals) if vals else 0.0
        sei_avg = np.mean([self.grid.get((xi, self.nr-1, "neg"), NodeState()).L_sei for xi in range(self.nx)])
        R_sei = self.p.rho_sei * sei_avg
        V_sei = self.I_applied * R_sei * self.p.a_neg * self.p.L_neg
        V = (avg_U("pos") + avg_eta("pos")) - (avg_U("neg") + avg_eta("neg")) - V_sei
        return max(2.5, min(4.5, V))

    def _compute_soc(self):
        vals = [np.mean([self.grid.get((xi, ri, "neg"), NodeState(c_s=15000)).c_s for ri in range(self.nr)]) for xi in range(self.nx) if (xi, 0, "neg") in self.grid]
        if not vals: return self.SOC
        x_avg = np.mean(vals) / self.p.c_s_max_neg
        return max(0.0, min(1.0, (x_avg - 0.02) / (0.88 - 0.02)))

    def _compute_soh(self):
        sei_vals = [self.grid.get((xi, self.nr-1, "neg"), NodeState()).L_sei for xi in range(self.nx) if (xi, self.nr-1, "neg") in self.grid]
        sei_avg = np.mean(sei_vals) if sei_vals else 5e-9
        lli = (sei_avg - 5e-9) / 5e-9 * 0.02
        return max(0.5, 1.0 - lli)

    def step(self, I_applied, dt=0.001):
        t0 = time.perf_counter()
        self.I_applied = I_applied
        self.step_count += 1
        volatile = self._detect_volatile_nodes()
        self.sparse_fraction = len(volatile) / max(1, len(self.active))
        for key in volatile:
            if self.grid[key].r == self.nr - 1:
                self._solve_reaction(key, I_applied)
        for key in volatile:
            self._solve_solid_diffusion(key, dt)
        self._solve_electrolyte(dt)
        surface_neg = self.grid.get((self.nx//2, self.nr-1, "neg"), NodeState())
        tco_state = {
            "j": surface_neg.j, "eta": surface_neg.eta,
            "U": surface_neg.U, "c_s": surface_neg.c_s,
            "c_e": surface_neg.c_e, "L_sei": surface_neg.L_sei,
            "d_eta_dt": self.d_eta_dt,
        }
        tco_out = self.tco.apply_all(tco_state, dt)
        self.V_terminal = self._compute_terminal_voltage()
        self.SOC = self._compute_soc()
        self.SOH = self._compute_soh()
        prev_eta = self.eta_anode
        self.eta_anode = surface_neg.eta
        self.d_eta_dt = (self.eta_anode - prev_eta) / max(dt, 1e-9)
        self.plating_risk = tco_out["plating_risk"]
        self.plating_onset_s = tco_out["plating_onset_seconds"]
        self.degradation_mode = tco_out["degradation_mode"]
        for key, node in self.grid.items():
            self.prev_c_s[key] = node.c_s
            self.prev_c_e[key] = node.c_e
        self.damage.clear()
        h = self._hidx % self.HIST
        self.hist_V[h] = self.V_terminal
        self.hist_I[h] = I_applied
        self.hist_SOC[h] = self.SOC
        self.hist_eta[h] = self.eta_anode
        self.hist_sei[h] = surface_neg.L_sei * 1e9
        self.hist_t[h] = self.step_count * dt
        self._hidx += 1
        self.t_elapsed += time.perf_counter() - t0
        return {
            "V": self.V_terminal, "I": self.I_applied,
            "SOC": self.SOC, "SOH": self.SOH,
            "eta_anode_mV": self.eta_anode * 1000.0,
            "plating_risk": self.plating_risk,
            "plating_onset_s": self.plating_onset_s,
            "degradation_mode": self.degradation_mode,
            "sei_nm": tco_out["sei_thickness_nm"],
            "tco_consistent": tco_out["globally_consistent"],
            "sparse_fraction": self.sparse_fraction,
            "step": self.step_count,
            "avg_step_us": (self.t_elapsed / max(1, self.step_count)) * 1e6,
        }

    def get_concentration_field(self, region="neg"):
        cs_max = self.p.c_s_max_neg if region == "neg" else self.p.c_s_max_pos
        field = np.zeros((self.nx, self.nr))
        for xi in range(self.nx):
            for ri in range(self.nr):
                node = self.grid.get((xi, ri, region))
                if node: field[xi, ri] = node.c_s / cs_max
        return field

    def get_eta_field(self):
        eta = np.zeros(self.nx)
        for xi in range(self.nx):
            node = self.grid.get((xi, self.nr-1, "neg"))
            if node: eta[xi] = node.eta * 1000.0
        return eta

    def get_sei_field(self):
        sei = np.zeros(self.nx)
        for xi in range(self.nx):
            node = self.grid.get((xi, self.nr-1, "neg"))
            if node: sei[xi] = node.L_sei * 1e9
        return sei

    def predict_rul(self):
        sei_avg = np.mean(self.get_sei_field())
        sei_rate = max(1e-6, sei_avg - 5.0) / max(1, self.step_count) * 1000
        cycles = int((50.0 - sei_avg) / max(1e-6, sei_rate))
        penalty = self.tco.bv_tco.plating_events * 5
        return min(5000, max(0, cycles - penalty))

    def get_causal_diagnosis(self):
        diag = self.tco.get_causal_diagnosis()
        diag["RUL_cycles"] = self.predict_rul()
        diag["SOC"] = self.SOC
        diag["SOH"] = self.SOH
        diag["V_terminal"] = self.V_terminal
        diag["eta_anode_mV"] = self.eta_anode * 1000.0
        diag["plating_risk_pct"] = self.plating_risk * 100.0
        return diag

    def reset(self):
        self.grid.clear()
        self.active.clear()
        self.damage.clear()
        self.prev_c_s.clear()
        self.prev_c_e.clear()
        self._init_grid()
        self.step_count = 0
        self.t_elapsed = 0.0
        self.SOC = 0.67
        self.SOH = 1.00
        self.tco.reset()
