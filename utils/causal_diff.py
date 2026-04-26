
import numpy as np
from typing import Dict, List, Optional

class CausalDiff:
    """
    Causal model comparison engine.
    Compares two battery models on physical consistency,
    not just MSE — the key innovation of OpenCATHODE benchmarking.

    Usage:
        diff = CausalDiff()
        report = diff.compare(model_a_results, model_b_results)
        print(diff.format_report(report))
    """

    def compare(self, model_a: Dict, model_b: Dict,
                name_a="OpenCATHODE", name_b="Baseline") -> Dict:
        report = {
            "model_a": name_a,
            "model_b": name_b,
            "metrics": {}
        }

        for key in ["SOH_pct", "RUL_cycles", "plating_events", "sei_nm"]:
            va = model_a.get(key, 0)
            vb = model_b.get(key, 0)
            report["metrics"][key] = {
                name_a: va,
                name_b: vb,
                "delta": va - vb,
                "delta_pct": ((va - vb) / max(abs(vb), 1e-9)) * 100
            }

        tco_a = model_a.get("tco_consistent", True)
        tco_b = model_b.get("tco_consistent", False)
        report["physics_consistency"] = {
            name_a: "VERIFIED" if tco_a else "VIOLATED",
            name_b: "VERIFIED" if tco_b else "VIOLATED",
        }

        mode_a = model_a.get("dominant_mode", "UNKNOWN")
        mode_b = model_b.get("dominant_mode", "UNKNOWN")
        report["degradation_attribution"] = {
            name_a: mode_a,
            name_b: mode_b,
            "agreement": mode_a == mode_b
        }

        return report

    def format_report(self, report: Dict) -> str:
        na = report["model_a"]
        nb = report["model_b"]
        lines = [
            "",
            "╔══════════════════════════════════════════════════════╗",
            f"║  CAUSAL DIFF: {na:20s} vs {nb:10s}  ║",
            "╠══════════════════════════════════════════════════════╣",
        ]
        for metric, vals in report["metrics"].items():
            va = vals[na]
            vb = vals[nb]
            d  = vals["delta_pct"]
            sign = "+" if d >= 0 else ""
            lines.append(f"║  {metric:20s}  {na}: {va:8.2f}  {nb}: {vb:8.2f}  Δ={sign}{d:.1f}%")
        lines.append("╠══════════════════════════════════════════════════════╣")
        pc = report["physics_consistency"]
        lines.append(f"║  Physics Consistency:  {na}: {pc[na]:10s}  {nb}: {pc[nb]:10s}  ║")
        da = report["degradation_attribution"]
        lines.append(f"║  Degradation Mode:     {na}: {da[na]:10s}  {nb}: {da[nb]:10s}  ║")
        lines.append("╚══════════════════════════════════════════════════════╝")
        return "\n".join(lines)
