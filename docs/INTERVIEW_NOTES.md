# Construction Project Control: Interview Notes & Practical Discussion

These notes provide concise, practical answers to common project control and engineering interview questions, referencing real figures and findings from this synthetic G+4 residential building project.

---

### 1. What is float and why does it matter?
Total float is the duration an activity can slip without delaying final project completion. It is calculated in the CPM backward pass as late start minus early start, or late finish minus early finish. In our project, ground-floor brickwork (BW_GF) has a total float of 143 wd. It can absorb site disruptions, mason shortages, or re-sequencing without affecting the handover date. In contrast, the second-floor slab (SLAB_F2) is on the critical path with 0 wd of total float. When SLAB_F2 slipped by 10 wd due to shuttering shortages, every lost day pushed downstream structural cycles and delayed handover by exactly 10 wd. Knowing float lets me allocate expediting resources where they count, rather than reacting to delays on non-critical work.

### 2. What do this project's month-6 SPI and CPI mean?
At Month 6 (30 Jun 2026), project CPI is 0.977 and SPI is 0.825. A CPI of 0.977 shows reasonable cost control: cumulative earned value is Rs 1,87,43,829 against actual cost of Rs 1,91,92,840. The cost overrun of Rs 4,49,012 comes mainly from the 10% steel price escalation active since Month 3. An SPI of 0.825 shows progress slippage in rupee terms, with earned value trailing planned value (Rs 2,27,18,667) by Rs 39,74,838. SPI is currency-weighted, not a day count. The 10 wd delay on SLAB_F2 pushed back structural framing on upper floors. Because of that, high-value finishing and service packages planned for late June could not start before 30 Jun 2026. These include top-floor brickwork BW_F4, plumbing rough-in PLUMB_RI, electrical rough-in ELEC_RI, and external works EXT. Pushing these costly activities out of June drops earned value compared to planned value, lowering SPI far more than the 10 wd slip alone suggests.

### 3. Why EAC = BAC / CPI, and when is it wrong?
Standard EAC = BAC / CPI divides Budget at Completion (Rs 3,81,13,500) by cumulative CPI (0.977). That projects a final cost of Rs 3,90,26,515 and an overrun of Rs 9,13,015. This formula assumes future work continues at past cost performance. That assumption breaks down when schedule delay forces site acceleration or extended site overheads. If the contractor must add gangs, work overtime, or expedite deliveries, unit costs will rise. Under those conditions, combined EAC = AC + (BAC - EV) / (CPI x SPI) gives a more realistic view. Dividing uncompleted work by CPI x SPI (0.977 x 0.825) penalizes the forecast for delay. For our project, combined EAC reaches Rs 4,32,32,468, showing higher financial exposure. I would present standard EAC for baseline tracking, and combined EAC when schedule recovery is needed.

### 4. How would you act on the slab delay?
When SLAB_F2 slipped by 10 wd due to shuttering material shortages, forecast handover moved from 07 Sep 2026 to 18 Sep 2026. Because superstructure framing has reached the roof by Month 6, structural crash options are over. Recovery must focus on remaining finishing and commissioning activities. I would convene a look-ahead session with site engineers and finishing subcontractors to re-sequence remaining packages. Rather than doing finishes sequentially across the whole building, I would overlap wall plastering and floor tiling floor by floor, adding a second plastering crew. In my 1-page report for the Regional Project Head, I would present this recovery plan with the cost of extra gangs. If 07 Sep 2026 is commercially binding, I would seek approval for acceleration costs. Otherwise, I would recommend agreeing on a revised handover date of 18 Sep 2026.

### 5. What is retention and why hold a bill for an open NCR?
Retention is a deduction from each gross progress bill (5% here) held by the owner. It protects against defects found later during the defect liability period. In our project, cumulative retention held through Month 6 reaches Rs 9,59,642 across RA-01 to RA-06. Retention protects the project after handover, but an open non-conformance needs immediate action during construction. In Month 6, NCR-003 for slab levels on SLAB_F3 has been open for 56 days. I hold bill RA-05 because you do not certify payment for work that failed inspection until it is fixed and re-inspected. Holding the bill also gives the contractor a clear reason to close the NCR quickly.

### 6. How was material requirement computed?
I calculate material requirements from BOQ quantities using the assumed coefficients in material_coefficients.csv. For each activity, planned work is multiplied by factors for cement bags, steel kg, sand cum, aggregate cum, and bricks. Baseline demand is spread linearly over planned working days, just like Planned Value. For site orders, our rule orders next month's forecast need plus a 5% buffer at the end of each month. Month 1 also buys Month 1 demand to build site stock. In Month 4, we simulated a cement shortage where procurement was cut to 70% of Month 5 need. The model flags this shortfall as a warning, but has no link from stock to progress, so it does not slow work in the simulation. In Month 6, cement closing stock was 634.8 bags, and Month 7 procurement is planned at 439.5 bags.

### 7. What did the negative-control test prove?
The negative-control test verifies that the warning rules trigger only on real problems. In tests/test_injected_issues.py (test_negative_control), I turn off all injected issues. That disables the 10 wd slab delay, the 10% steel price escalation, the Month 4 cement shortage, the quality NCRs, and payment holds. The simulation draws random background noise upfront in activities.csv order, giving identical noise draws with or without injections. With injections off, the project has 0 red and 0 amber warning flags across all 6 evaluation months. Monthly SPI and CPI stay at or above 0.95, and forecast handover delay is 0 wd. This proves two things: first, that background noise (+/-3%) does not trigger false alarms; second, that every warning flag in Month 6 comes directly from the injected issues.

### 8. What would you do differently with real site data?
Real site execution has complexities that a synthetic model simplifies. First, I would track actual work with daily pouring logs, measurement sheets, and bar bending schedules rather than linear spreading. Second, I would add start-to-start and finish-to-finish links with leads and lags. For example, brickwork could start a few days after column de-shuttering instead of waiting for a full floor cycle. I would also add resource levelling for cranes, concrete pumps, and formwork sets. Third, on the commercial side, I would track quantity variations against contract limits, manage delay claims, and reconcile purchase invoices against theoretical usage to spot wastage. Fourth, for quality, I would use digital checklists linked to 7-day cube test certificates and lab test reports. Finally, I would run Monte Carlo schedule risk analysis on remaining paths.

### 9. Why is the CPM-based forecast better than duration / SPI, and what does TCPI 1.024 tell you?
The CPM forecast is better than duration divided by SPI because it follows the network logic and working calendar. Dividing planned duration (211 wd) by SPI (0.825) gives a crude forecast of 256 wd, implying a 45 wd delay to 29 Oct 2026. That formula assumes all remaining work will run at the same slow rate (82.5% of plan). In fact, the delay was a one-off on one slab (SLAB_F2). The remaining activities are expected to take their planned durations. CPM moves handover by the 10 wd already lost and no more, forecasting completion on 18 Sep 2026. TCPI of 1.024 shows the cost performance needed on remaining work to finish within the BAC of Rs 3,81,13,500. Since historical CPI is 0.977, achieving 1.024 requires a modest efficiency improvement.

---

### 10. If asked about the code
- `src/budget.py`: Computes activity budgets from BOQ quantities and rates, and spreads planned value linearly across working days.
- `src/charts.py`: Generates EVM S-curves and baseline vs forecast Gantt comparison charts using matplotlib.
- `src/data_io.py`: Loads and validates CSV and YAML data files into structured pandas DataFrames.
- `src/evm.py`: Calculates Earned Value Management metrics, completion forecasts, and cost variances.
- `src/flags.py`: Evaluates warning threshold rules across 9 categories and prioritizes the top 5 issues.
- `src/materials.py`: Tracks raw material consumption, inventory balances, and forward purchase requirements.
- `src/payments.py`: Manages monthly RA bills, calculates retention and TDS deductions, and tracks payment lifecycles.
- `src/pipeline.py`: Coordinates the overall pipeline, monthly reporting views, and results export.
- `src/quality.py`: Maintains quality inspection registers, pass rates, and non-conformance logs.
- `src/report.py`: Generates the 1-page report for the Regional Project Head and multi-sheet Excel workbook.
- `src/schedule.py`: Implements Critical Path Method (CPM) forward/backward passes, float calculations, and schedule forecasting.
- `src/sensitivity.py`: Runs multi-parameter what-if sensitivity scans on steel escalation and schedule delays.
- `src/simulate.py`: Simulates monthly actuals, seeded random noise, and injected operational issues.
