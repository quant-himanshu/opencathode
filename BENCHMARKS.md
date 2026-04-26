# OpenCATHODE — Cross-Dataset Validation

**Theil-Sen robust estimator | first 10 cycles only | zero retuning**

| Dataset | Chemistry | R² | MAE | Result |
|---------|-----------|-----|-----|--------|
| NASA-B18 | NMC (NASA) | 0.9844 | 0.0033 | ✅ |
| Oxford-LCO | LCO (Oxford) | 0.9466 | 0.0171 | ✅ |
| CALCE-LCO | LCO (CALCE) | 0.9750 | 0.0192 | ✅ |

**Average R² = 0.9687**

- Estimator: Theil-Sen (robust to noise, Severson 2019 method)
- EKF SOC error: 0.77% after convergence
- Real-time: 29-30 FPS
- Author: Himanshu Sharma, AMU EV Engineering
