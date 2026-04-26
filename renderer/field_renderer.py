
import numpy as np
import sys
import os
import time
import math
from typing import Optional

# ANSI escape codes
ESC = "\033"
RESET = f"{ESC}[0m"
BOLD = f"{ESC}[1m"
DIM = f"{ESC}[2m"

def ansi_fg(r, g, b): return f"{ESC}[38;2;{r};{g};{b}m"
def ansi_bg(r, g, b): return f"{ESC}[48;2;{r};{g};{b}m"
def cursor_to(row, col): return f"{ESC}[{row};{col}H"
def clear_screen(): return f"{ESC}[2J{ESC}[H"
def hide_cursor(): return f"{ESC}[?25l"
def show_cursor(): return f"{ESC}[?25h"

BRAILLE = "⠀⠁⠂⠃⠄⠅⠆⠇⡀⡁⡂⡃⡄⡅⡆⡇⠈⠉⠊⠋⠌⠍⠎⠏⡈⡉⡊⡋⡌⡍⡎⡏⠐⠑⠒⠓⠔⠕⠖⠗⡐⡑⡒⡓⡔⡕⡖⡗⠘⠙⠚⠛⠜⠝⠞⠟⡘⡙⡚⡛⡜⡝⡞⡟"
BLOCKS   = " ░▒▓█"

def value_to_color(v, vmin=0.0, vmax=1.0, mode="heat"):
    t = max(0.0, min(1.0, (v - vmin) / max(1e-9, vmax - vmin)))
    if mode == "heat":
        if t < 0.25:
            r,g,b = int(0+t*4*0),    int(0+t*4*100),  int(180-t*4*50)
        elif t < 0.5:
            r,g,b = int(0+(t-0.25)*4*100), int(100+(t-0.25)*4*155), int(130-(t-0.25)*4*130)
        elif t < 0.75:
            r,g,b = int(100+(t-0.5)*4*155), int(255-(t-0.5)*4*100), int(0)
        else:
            r,g,b = int(255), int(155-(t-0.75)*4*155), int(0)
        return r,g,b
    elif mode == "risk":
        r = int(t * 255)
        g = int((1-t) * 200)
        b = 0
        return r,g,b
    else:
        v2 = int(t * 255)
        return v2, v2, v2

class TerminalFieldRenderer:
    """
    60fps terminal renderer for electrochemical fields.
    Damage-tracking diffing: only redraws changed cells.
    Inspired by ink/output.ts blit() optimisation.
    """
    WIDTH  = 80
    HEIGHT = 24

    def __init__(self):
        self.prev_frame = {}
        self.frame_count = 0
        self.t_last = time.perf_counter()
        self.fps = 0.0
        self._buf = []
        os.system("clear")
        sys.stdout.write(hide_cursor())
        sys.stdout.flush()

    def _buf_write(self, row, col, text, r=255, g=255, b=255, bg=None):
        key = (row, col)
        val = (text, r, g, b)
        if self.prev_frame.get(key) == val:
            return  # blit optimisation — skip unchanged
        self.prev_frame[key] = val
        s = cursor_to(row, col) + ansi_fg(r, g, b)
        if bg: s += ansi_bg(*bg)
        s += text + RESET
        self._buf.append(s)

    def _flush(self):
        sys.stdout.write("".join(self._buf))
        sys.stdout.flush()
        self._buf.clear()
        sys.stdout.write("[H")
        sys.stdout.flush()

    def render_dashboard(self, obs, step_count=0):
        """Full 60fps dashboard render."""
        now = time.perf_counter()
        dt = now - self.t_last
        self.fps = 0.9 * self.fps + 0.1 * (1.0 / max(dt, 1e-6))
        self.t_last = now
        self.frame_count += 1

        # ── Header ──────────────────────────────────────────────
        self._buf_write(1, 1, "█"*78, 30, 30, 40, bg=(20,20,35))
        title = " ⚡ OPENCATHODE v1.0  —  Real-Time Electrochemical Terminal "
        self._buf_write(1, 2, title, 80, 200, 255)
        self._buf_write(1, 65, f"FPS:{self.fps:5.1f}", 100, 255, 100)

        # ── Status line ──────────────────────────────────────────
        V   = obs.V_terminal
        SOC = obs.SOC * 100
        SOH = obs.SOH * 100
        eta = obs.eta_anode * 1000
        risk= obs.plating_risk * 100
        mode= obs.degradation_mode

        vr,vg,vb = (100,255,100) if V > 3.2 else (255,200,0)
        self._buf_write(2, 2,  f"V ={V:6.3f}V", vr,vg,vb)
        self._buf_write(2, 16, f"SOC={SOC:5.1f}%", 100,200,255)
        self._buf_write(2, 30, f"SOH={SOH:5.1f}%", 100,255,200)
        self._buf_write(2, 44, f"η ={eta:+6.1f}mV", *self._eta_color(eta))
        self._buf_write(2, 58, f"MODE:{mode:12s}", *self._mode_color(mode))

        # ── Concentration field ───────────────────────────────────
        self._buf_write(3, 2, "─"*76, 60,60,80)
        self._buf_write(4, 2, " NEGATIVE ELECTRODE — Li Concentration Field", 160,160,200)
        c_field = obs.get_concentration_field("neg")  # [nx, nr]
        nx, nr = c_field.shape
        bar_w = min(72, nx * 3)
        for xi in range(min(nx, bar_w//3)):
            c_avg = np.mean(c_field[xi, :])
            r2,g2,b2 = value_to_color(c_avg, 0.0, 1.0, "heat")
            char = BLOCKS[min(4, int(c_avg * 5))]
            self._buf_write(5, 2 + xi*3,     char*3, r2,g2,b2)
        self._buf_write(6, 2, "0%", 120,120,140)
        self._buf_write(6, bar_w-4, "100%", 120,120,140)

        # ── Overpotential field ───────────────────────────────────
        self._buf_write(7, 2, "─"*76, 60,60,80)
        self._buf_write(8, 2, " OVERPOTENTIAL FIELD  η(x) [mV]  — PLATING THRESHOLD: -15mV", 160,160,200)
        eta_field = obs.get_eta_field()
        for xi in range(min(len(eta_field), bar_w//3)):
            eta_v = eta_field[xi]
            r2,g2,b2 = value_to_color(-eta_v, -30, 0, "risk")
            marker = "▼" if eta_v < -15 else ("▽" if eta_v < -10 else "│")
            self._buf_write(9, 2 + xi*3, marker*3, r2,g2,b2)
        # Threshold line
        self._buf_write(10, 2, "PLATING THRESHOLD " + "─"*50 + " -15mV", 255,80,80)

        # ── SEI thickness field ───────────────────────────────────
        self._buf_write(11, 2, "─"*76, 60,60,80)
        self._buf_write(12, 2, " SEI THICKNESS FIELD [nm]", 160,160,200)
        sei_field = obs.get_sei_field()
        sei_max = max(max(sei_field), 5.1)
        for xi in range(min(len(sei_field), bar_w//3)):
            sv = sei_field[xi]
            r2,g2,b2 = value_to_color(sv, 5.0, 20.0, "heat")
            char = BLOCKS[min(4, int((sv-5.0)/(sei_max-5.0+1e-9)*5))]
            self._buf_write(13, 2 + xi*3, char*3, r2,g2,b2)

        # ── Plating risk gauge ────────────────────────────────────
        self._buf_write(14, 2, "─"*76, 60,60,80)
        self._buf_write(15, 2, " LITHIUM PLATING RISK", 160,160,200)
        gauge_w = 50
        filled = int(risk / 100.0 * gauge_w)
        rg,gg,bg2 = value_to_color(risk/100, 0, 1, "risk")
        bar = "█"*filled + "░"*(gauge_w-filled)
        self._buf_write(15, 24, f"[{bar}] {risk:5.1f}%", rg,gg,bg2)

        # Plating onset warning
        onset = obs.plating_onset_s
        if onset is not None and onset < 60:
            warn = f"  ⚠  PLATING ONSET IN {onset:.1f}s  ⚠  "
            self._buf_write(16, 20, warn, 255, 50, 50)
        elif eta < -10:
            self._buf_write(16, 20, "  ⚡ APPROACHING PLATING THRESHOLD — MONITOR  ", 255,200,0)
        else:
            self._buf_write(16, 20, " "*50, 60,60,80)

        # ── Causal diagnosis ──────────────────────────────────────
        self._buf_write(17, 2, "─"*76, 60,60,80)
        diag = obs.get_causal_diagnosis()
        dom  = diag.get("dominant_mode","STABLE")
        rul  = diag.get("RUL_cycles", 0)
        sei  = diag.get("sei_thickness_nm", 5.0)
        plat = diag.get("plating_events", 0)
        self._buf_write(18, 2,  f" CAUSAL DIAGNOSIS:", 200,200,255)
        self._buf_write(18, 22, f"Mode:{dom:12s}", *self._mode_color(dom))
        self._buf_write(18, 42, f"RUL:{rul:5d}cyc", 100,255,200)
        self._buf_write(19, 2,  f" SEI:{sei:6.2f}nm", 180,180,255)
        self._buf_write(19, 18, f"PlatingEvents:{plat:4d}", 255,160,100)
        self._buf_write(19, 40, f"Step:{step_count:8d}", 120,120,150)
        self._buf_write(19, 58, f"Sparse:{obs.sparse_fraction*100:5.1f}%", 100,200,100)

        # ── Vim command line ──────────────────────────────────────
        self._buf_write(20, 2, "─"*76, 60,60,80)
        self._buf_write(21, 2, " COMMANDS: [i]charge  [d]discharge  [s]status  [q]quit  [p]passport  [r]reset", 120,180,255)
        self._buf_write(22, 2, "─"*76, 60,60,80)

        self._flush()

    def _eta_color(self, eta_mV):
        if eta_mV < -15: return 255,50,50
        if eta_mV < -10: return 255,200,0
        return 100,255,100

    def _mode_color(self, mode):
        m = {"STABLE":(100,255,100),"SEI_GROWTH":(255,200,0),
             "PLATING":(255,50,50),"LLI":(200,100,255)}
        return m.get(mode,(200,200,200))

    def cleanup(self):
        sys.stdout.write(show_cursor())
        os.system("clear")
        sys.stdout.flush()
