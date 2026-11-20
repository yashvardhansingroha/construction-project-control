# Construction Project Control: Methodology & Engineering Assumptions

## Assumptions at a Glance

| Parameter | Baseline Value | Reference / Governance Notes |
|---|---|---|
| Project Type | G+4 Residential RCC Frame (Synthetic) | Gross built-up area 2,000 sqm across 5 floors; footprint 400 sqm |
| Working Calendar | 6-day week (Mon-Sat), Sunday off | Start date: 2026-01-05 (Monday); Data date: 2026-06-30 (Month 6); 0 holidays |
| Budget at Completion (BAC) | INR 38,113,500 | Sum of 13 BOQ items (quantity x rate); direct cost without separate contingency |
| Rates & Assumptions | Illustrative engineering assumptions | Round assumed figures for demonstration; not from CPWD DSR or official schedules |
| Statutory Deductions | Retention: 5%, TDS: 2% | Monthly bill cycle submitted on calendar month end; 7d certification, 14d payment |
| Monitoring Thresholds | SPI/CPI: 0.95 (amber), 0.90 (red) | Milestone slip: 5 wd (amber), 10 wd (red); NCR: 14 days; Bill pending: 30 days |
| Background Noise | Progress SD: 0.03; Cost SD: 0.02 | Seed 42; cost noise clipped to +/-3%; non-critical activities only; drawn upfront |
| Injected Issues | Master switch enabled | SLAB_F2 delay (+10 wd), steel escalation (+10% from M3), M4 cement shortage (30%), 3 QC failures, RA-05 hold |

---

## 1. Building and Data Assumptions

### 1.1 Building Description
- Type: G+4 Residential RCC Frame Building (Synthetic Model).
- Built-up Area: 2,000 sqm total gross built-up area across 5 floors (Ground Floor + 4 upper floors).
- Footprint: 400 sqm per floor plate.
- Substructure: Isolated reinforced concrete footings with tied plinth beams on PCC bedding under footings.
- Superstructure: Cast-in-place RCC frame comprising columns, beams, and two-way slabs (RCC M25 with Fe500 reinforcement steel).

### 1.2 Working Calendar & Project Timeframe
- Start Date: Monday, 5 January 2026.
- Working Week: 6-day working week (Monday through Saturday, Sundays off), 0 official holidays modelled.
- Data Date: 30 June 2026 (end of Month 6 status date).
- Project Months: Calendar months align with project months (Month 1 = January 2026, Month 6 = June 2026).
- Baseline Duration: Longest path is 211 working days (~35.2 working weeks, approximately 8 calendar months), within the 195 to 215 working day target.

### 1.3 Bill of Quantities (BOQ) Derivation & Engineering Ratios
All quantities relate directly to the 2,000 sqm built-up area using assumed illustrative ratios:
- Excavation (EXC): 650 cum (~1.625 cum per sqm of ground footprint) for isolated footing pits, column pads, and plinth trenching.
- PCC M10 (PCC): 45 cum (PCC bedding under footings).
- RCC M25 (RCC_M25): 820 cum = 0.41 cum per sqm of built-up area, distributed across footings (15%), plinth beams (10%), 5 column lifts (3% each = 15%), and 5 suspended slab/beam levels (12% each = 60%).
- Reinforcement Steel (STEEL): 90 MT (90,000 kg Fe500) = 109.76 kg per cum of RCC (~110 kg/cum), consistent with typical residential frame reinforcement intensity. Steel allocation directly follows concrete placement per activity.
- Brickwork (BRICK): 520 cum = 0.26 cum per sqm built-up area (230 mm thick external perimeter masonry and internal compartment walls), split evenly at 104 cum (20%) per floor across 5 levels.
- Plastering (PLASTER): 7,600 sqm = 3.8 sqm per sqm built-up area (internal walls, ceilings, and external elevation plastering in CM 1:4).
- Flooring (FLOOR): 1,750 sqm = 0.875 sqm per sqm built-up area (~88% net carpet/circulation area after wall thicknesses and service shafts).
- Doors and Windows (DW): 190 nos (~38 openings per floor for entrance doors, internal flush doors, UPVC/aluminium windows, and ventilators).
- Painting (PAINT): 7,600 sqm matching plaster area (primer, putty, and 2 coats of internal acrylic emulsion / external weatherproof paint).
- Plumbing & Electrical Packages (PLUMB, ELEC): Complete internal and external MEP installations modelled as lump-sum packages, split 85% rough-in works and 15% final fixtures/testing.
- External Works (EXT): Lump-sum package covering compound wall, boundary gates, storm-water drainage, and site paving.

### 1.4 Illustrative Nature of Rates and Coefficients
All unit rates, quantities, and material consumption coefficients are illustrative baseline assumptions chosen for educational clarity and synthetic EVM demonstration. They do not represent official schedules such as the CPWD Delhi Schedule of Rates (DSR) or state PWD schedules:
- Budget at Completion (BAC): Sum of BOQ quantity x rate = INR 38,113,500 (INR 19,056.75 per sqm of built-up area, or ~INR 1,770 per sq ft).
- Direct BOQ Costing: BAC excludes separate contingency or contractor margin lines so that EVM formulas remain completely transparent.

### 1.5 Floor & Slab Naming Conventions
- Ground Floor structure comprises footings, plinth beams, and ground-floor columns (COL_GF).
- The slab cast immediately above ground-floor columns is the 1st-floor slab (SLAB_F1).
- The "2nd-floor slab" referenced in the project brief corresponds exactly to activity SLAB_F2 (the slab cast at 2nd-floor level above columns COL_F1).
- The top suspended slab is SLAB_ROOF cast above 4th-floor columns (COL_F4).

### 1.6 Activity Durations and Critical Path Rationale
- Substructure Chain (40 days): Site mobilisation (6d) -> excavation (8d) -> PCC bedding (4d) -> footing reinforcement, shuttering and concreting (14d) -> plinth beams and backfill (8d) -> Plinth Milestone (M_PLINTH, 0d).
- Superstructure Cycles (100 days): 5 repetitive floor cycles of 20 days each. Each cycle consists of column reinforcement/shuttering/concreting (5d), slab and beam shuttering/reinforcement/concreting (9d), and an assumed 6-working-day curing / de-shuttering gap before the next lift starts (CURE_*).
- Critical Path Backbone: The structural RCC chain (MOB through CURE_ROOF) forms the project critical path (total float = 0). Floor brickwork (BW_GF through BW_F3) starts once the respective floor's slab is cured and proceeds in parallel with higher-level structural framing with positive float (83 to 143 days float).
- Finishes and Handover (71 days): Finishes commence after roof curing and top-floor brickwork (BW_F4), proceeding through plumbing and electrical rough-ins (12d), plastering (18d), flooring (14d), painting (12d), testing/commissioning (7d), and final handover milestone (M_HANDOVER, 0d), giving a total baseline longest path of 211 working days.

---

## 2. Schedule (CPM)

### 2.1 Critical Path Method Formulation
The schedule network operates on finish-to-start dependencies with zero lag across working days:

1. Forward Pass (Early Dates):
   - Early Start (ES):
     ES = 0 if activity has no predecessors
     ES = max(EF of predecessors) otherwise
   - Early Finish (EF):
     EF = ES + duration
   - Project Planned Duration (T):
     T = max(EF of all activities)

2. Backward Pass (Late Dates):
   - Late Finish (LF):
     LF = T if activity has no successors
     LF = min(LS of successors) otherwise
   - Late Start (LS):
     LS = LF - duration

3. Float and Criticality:
   - Total Float (TF):
     TF = LS - ES = LF - EF
   - Critical Activity: An activity is critical if and only if TF = 0. The critical path forms a continuous chain from MOB to M_HANDOVER.

### 2.2 Calendar and Date Conventions
- Calendar: 6 working days per week (Monday through Saturday, Sundays off), 0 official holidays.
- Working Day Index: Integer n >= 0, where n = 0 is Monday, 5 January 2026.
- Start Date: start_date = wd_to_date(ES).
- Finish Date:
  - For work and curing activities (duration > 0): finish_date = wd_to_date(EF - 1), representing the final working day during which work is executed.
  - For milestones (duration = 0): finish_date = wd_to_date(EF - 1) if EF > 0 (the date the last preceding task finished), or start_date if EF = 0.
- Project Baseline Handover Date: Working day index 210 of the 211 working day duration lands exactly on Monday, 7 September 2026.

### 2.3 CPM Schedule Forecast Rules
At any project data date (Month 6 data date = Day 152), activities are classified into three operational states:
1. Done:
   ES = actual_start, EF = actual_finish
2. In Progress:
   ES = actual_start, EF = data_date_wd + remaining_days
3. Not Started:
   ES = max(data_date_wd, max(EF of predecessors)), EF = ES + planned_duration

The backward pass is executed against updated forecast project completion date max(EF) using effective durations (EF - ES) to dynamically recompute remaining total float and identify the updated critical path. Float for completed activities is historical and not operationally actionable.

### 2.4 Network Integrity and Error Handling
The engine implements strict structural validations:
- Missing Predecessors: Validates that all IDs referenced in dependency lists exist in the WBS; raises MissingPredecessorError naming the activity and missing ID.
- Acyclicity via Kahn's Algorithm: Tracks node in-degrees; raises CycleError naming the cycle candidates if circular dependencies exist.
- Single Start Node: Enforces exactly one activity with zero predecessors (MOB).
- Milestone Validation: Confirms milestones have duration 0 and empty BOQ allocations.

---

## 3. Budget and Planned Value (PV)

### 3.1 Activity Budget Derivation
Each activity's budget is derived from its allocated shares of items in the Bill of Quantities (boq.csv):
- item_quantity = activity_share x BOQ_quantity
- amount = item_quantity x rate
- activity_budget = sum of item amounts
- Milestones and curing intervals carry zero budget.
- Total Budget at Completion (BAC): BAC = sum of all activity budgets = INR 38,113,500.

### 3.2 Linear Time-Phased Cost Spreading & Cumulative Rounding Rule
For any activity with budget B and planned duration D days starting at working day ES and completing at EF:
- Planned cost per working day: c = B / D.
- Cumulative working days worked through month m: C_m.
- Rupee-Exact Cumulative Rounding:
  cum_rounded_m = round(B x C_m / D)
  PV_m = cum_rounded_m - cum_rounded_(m-1)
This discrete accumulation formula prevents fractional-rupee drift, so sum(PV) equals BAC to the exact rupee.

---

## 4. Simulation Engine

### 4.1 Seeded Random Draw Sequence
The simulation runs deterministically using NumPy's modern Generator API (numpy.random.default_rng(seed=42)):
- Draw Sequence: Random progress noise and cost noise are drawn upfront in the exact row order of activities.csv for every activity, whether injections are active or not. This design preserves identical noise draws between injection runs and negative control runs.
- Progress Noise: d_noise drawn from Normal(0, 0.03) per activity.
  - Critical activities (from baseline CPM) keep exact planned durations without noise.
  - Non-critical work activities: actual_duration = max(1, round(planned_duration x (1 + d_noise))).
- Cost Noise: c_noise drawn from Normal(0, 0.02), clipped to [-3%, +3%]. Applied only to non-critical work. Because noise is capped at +/-3%, noise alone cannot breach the 5% activity cost-variance threshold.

### 4.2 Injected Issues
When injections are enabled (injections_enabled: true):
1. Critical Path Slab Delay (slab_delay): Activity SLAB_F2 (2nd-floor slab) receives +10 working days of duration (increased from 9d to 19d) due to a shuttering material shortage.
2. Steel Price Escalation (steel_escalation): From Month 3 onwards (m >= 3), all placed reinforcement steel (STEEL) experiences a +10% unit rate uplift (escalating from INR 72,000/MT to INR 79,200/MT).
3. Cement Shortage (cement_shortage): In Month 4, procured cement is restricted to 70% of Month 5 requirement.
4. Quality Non-Conformances: Three distinct QC failures (SLAB_F1 cube test, COL_F2 rebar spacing, SLAB_F3 surface level).
5. Commercial Payment Issues: RA-05 payment held due to open structural NCR-003; RA-03 paid late after 45 days.

### 4.3 Physical Work Measurement & Actual Cost (AC)
- Work progress is tracked by physical quantity placed:
  quantity_placed_in_month = planned_quantity x change_in_pct_complete
- Actual unit rate:
  actual_rate = baseline_rate x (1 + cost_noise) x (1 + steel_uplift)
- Actual Cost incurred:
  AC_month = sum over items of (quantity_placed x actual_rate)
- Modelling Limitation: Physical quantities placed equal design quantities (zero quantity overrun). All cost variances stem from unit price escalation and minor non-critical rate fluctuations.

---

## 5. Earned Value Management (EVM)

### 5.1 Core Metrics & Indices
Cumulative metrics at the end of each evaluation month m:
- Planned Value (PV): Baseline cumulative spend scheduled to date: sum(PV_k).
- Earned Value (EV): Value of physical work accomplished at contract rates:
  EV = sum(activity_budget x pct_complete)
- Actual Cost (AC): Cumulative expenditure incurred for work performed: sum(AC_k).
- Schedule Variance (SV): SV = EV - PV (negative indicates schedule delay).
- Cost Variance (CV): CV = EV - AC (negative indicates budget overrun).
- Schedule Performance Index (SPI): SPI = EV / PV.
- Cost Performance Index (CPI): CPI = EV / AC.
- In Month 6, SPI drops to 0.825 because the 10-working-day delay on SLAB_F2 cascades through the superstructure network, pushing high-value late June work (BW_F4, PLUMB_RI, ELEC_RI, and EXT) past the Month 6 data date.

### 5.2 Completion Forecasting
1. Standard EAC:
   EAC = BAC / CPI
   Assumes current cost efficiency CPI represents future contractor performance across remaining scope.
2. Combined EAC:
   EAC_combined = AC + (BAC - EV) / (CPI x SPI)
   The combined formula reflects real-world project dynamics where schedule delays force expensive acceleration measures (overtime, additional scaffolding, expedited material deliveries) or extended contractor overheads.
3. Estimate to Complete (ETC): ETC = EAC - AC.
4. Variance at Completion (VAC): VAC = BAC - EAC.
5. To-Complete Performance Index (TCPI):
   TCPI = (BAC - EV) / (BAC - AC)
   The efficiency factor required on remaining work to finish within the original budget.

### 5.3 Edge Case Conventions
- PV = 0: SPI and EAC_combined return None.
- AC = 0: CPI returns None, and EAC defaults to BAC (zero cost history implies planned budget).
- Project 100% complete (EV = BAC): TCPI = 0.0, ETC = 0.
- Budget fully exhausted (BAC = AC): TCPI returns None (division by zero).

### 5.4 Schedule Forecasting: Crude vs CPM Network
- Crude Forecast: crude_duration = round(planned_duration / SPI). A simple macro-level metric that treats all activities uniformly, ignoring non-critical float and actual network topology.
- CPM Network Forecast: Evaluates uncompleted tasks and remaining durations from the data date onward through forward pass scheduling. Identifies true critical bottlenecks and provides the definitive completion date.

---

## 6. Materials Quantification & Inventory Control

### 6.1 Material Requirements
Raw materials are converted from BOQ item quantities using assumed coefficients from material_coefficients.csv:
- material_need = sum over items of (BOQ_quantity x coefficient)
for materials: cement_bags, steel_kg, sand_cum, aggregate_cum, and bricks.

### 6.2 Baseline Requirement and Actual Consumption
- Baseline Requirement: Derived from the baseline CPM schedule by spreading each activity's mapped item quantities linearly across its scheduled working days (identical to PV linear spreading). The sum over all months equals total BOQ material needs.
- Actual Consumption: Derived directly from quantities placed in sim.ac_monthly for months 1 to 6.

### 6.3 Forecast Need and Procurement Ledger
- Forecast Requirement: Evaluated at month-end m for month m+1 by spreading remaining work linearly across the uncompleted working days of each activity falling in month m+1 under forecast_cpm.
- Procurement Simulation:
  - Month 1: Procures consumption of month 1 plus forecast need of month 2 (establishing initial site buffer).
  - Month m >= 2: Procures forecast requirement of month m+1 with a 5% buffer (1.05 x need_(m+1)).
  - Injection Exception (cement_shortage): In Month 4, cement supply is restricted to 70% of Month 5 requirement (0.70 x need_5, zero buffer).
- Stock Ledger Balance:
  Closing Stock = Opening Stock + Procured - Consumed
  Shortfall is flagged whenever Procured < Required_next_month.

---

## 7. Payments & RA Billing Engine

### 7.1 Monthly Gross Bills and Price Variation
Running Account (RA) bills are generated on the last calendar day of each month (RA-01 to RA-06):
- Gross Bill Amount: Equals actual cost incurred for work performed in that month: sum(sim.ac_monthly).
- Decomposition: Shown as work_at_boq_rates (physical EV increment at baseline rates) and price_variation (contractual price escalation on steel plus allowable market variance). This reflects a standard contract with price adjustment, ensuring cumulative actual cost (AC) matches the sum of gross bills to the exact rupee.

### 7.2 Statutory Deductions & Net Payable
Deductions are rounded to whole rupees to maintain exact integer identity:
- Retention: retention = round(gross x 0.05) (5% retention).
- TDS: tds = round(gross x 0.02) (2% tax deducted at source).
- Net Payable: net_payable = gross - retention - tds.

### 7.3 Payment Lifecycle & Injections
- Standard cycle: Submitted on month end, certified in 7 calendar days, paid 14 days after certification (21 days post-submission).
- Injected Payment Issues:
  - RA-03: Paid late after 45 days (submitted 31 Mar, paid 15 May).
  - RA-05: Placed on payment hold (status Held, zero paid date) due to open structural NCR-003 on SLAB_F3.

---

## 8. Quality Control & Non-Conformance Log

### 8.1 Inspection Framework
Quality inspections are conducted automatically against actual schedule dates:
- reinforcement_check: Conducted on the start date of all reinforced concrete activities (FTG, PLB, columns, slabs).
- cube_test: Conducted 7 calendar days after casting of all RCC activities (7-day compressive strength).
- slab_level_check: Conducted on the finish date of all slab pours.
- brickwork_plumb: Conducted on the finish date of all masonry lifts.

### 8.2 Injected Non-Conformances (NCRs)
1. NCR-001 (SLAB_F1 cube test): 7-day cube test fails compressive strength on 14 Mar 2026; rectified with core testing and approved non-shrink grouting, closed in 9 days (23 Mar 2026).
2. NCR-002 (COL_F2 reinforcement check): Rebar cover displacement detected on 20 Apr 2026; rectified with re-tying and extra cover blocks, closed in 20 days (10 May 2026).
3. NCR-003 (SLAB_F3 slab level check): Surface level tolerance breach flagged on 5 May 2026; requires joint structural consultant review, remains unresolved through Month 6 data date (56 days open).

---

## 9. Early Warning Health Flags

### 9.1 Rule Categories and Thresholds
Project warning flags use standardized category names matching underlying rule specifications:
1. milestone_slip: Unachieved milestone slip in forecast CPM vs baseline (>5 wd amber, >=10 wd red).
2. critical_behind: Evaluated for work activities on the baseline-critical path (excluding curing gaps and milestone markers). Flags when actual progress is >5 percentage points behind baseline schedule (amber; >50 points red). Includes a specific root-cause diagnosis field reason:
   - "started late by N wd (knock-on)": Triggered when actual start is delayed relative to baseline early start while activity execution duration conforms to plan. Action: Re-plan the look-ahead; protect the remaining float; no extra crew unless the handover date must be held.
   - "progressing slower than planned": Triggered when activity execution duration exceeds plan (SLAB_F2). Action: Find the constraint (here: shuttering material) and add resources to this activity.
3. spi / cpi: Monthly project-level indices <0.95 amber, <0.90 red.
4. activity_cost: Activity cost variance |(AC - EV) / EV| > 5% amber.
5. item_cost: BOQ item rate variance >5% amber, >15% red.
6. material_shortfall: Next month's procurement deficit relative to forecast need (>0% amber, >20% red).
7. ncr_ageing: NCR open during the month exceeding 14 days (amber if resolved before month end, red if unresolved at month end).
8. payment: RA bill on payment hold (red); bill pending certification/payment >30 days (amber); bill paid during the month >30 days after submission (amber paid late).

### 9.2 Prioritization and Top-5 Ranking
- Full Flag List: Sorted with red severity ahead of amber, sub-sorted descending by numerical magnitude.
- Top-5 Ranking: Avoids mixing different units (%, days, wd, index values) by employing a fixed category hierarchy:
  1. milestone_slip (M_HANDOVER only, with cascade text "also moves M_FINISH")
  2. spi
  3. cpi
  4. critical_behind
  5. material_shortfall
  6. ncr_ageing
  7. payment
  8. item_cost
  9. activity_cost
  Red severities take precedence over amber, at most one issue is selected per category, and numerical magnitude breaks ties within the same category. In Month 6, this deterministically yields: [milestone_slip M_HANDOVER, spi, critical_behind, ncr_ageing NCR-003, payment RA-05].

---

## 10. Outputs & Reporting Architecture

### 10.1 Month-View Data Contract & Overall Status Rule
The function month_view(m, injections_enabled=None) provides a complete monthly data package for reporting dashboards and project reports, cached to avoid redundant schedule and simulation passes:
- EVM Context: Monthly EVM rows for months 1 to m and the single-month headline block.
- Schedule Lookahead: Forecast CPM milestones evaluated at month-end data date with baseline dates, forecast dates, and working day slips.
- Flag Registers: All active early warning flags for month m and the ranked Top 5 issues.
- Procurement & Stocks: Material stock ledger for month m and forward purchase plan for month m+1.
- Financial Status: Contractor RA billing register evaluated at the month-end calendar date.
- Quality Assurance: Complete QC inspection ledger, pass statistics, and active NCR register.
- Overall Project Status Evaluation Rule (FROZEN):
  - RED: Triggered if any red flag exists in core performance categories: milestone_slip, spi, or cpi.
  - AMBER: Triggered if not red, but any red or amber flag exists across any category.
  - GREEN: Triggered if no red or amber flags are active.
  In Month 6, the project evaluates to RED due to milestone_slip (M_HANDOVER +10 wd) and spi (0.825 < 0.90).

### 10.2 Multi-Sheet Excel Workbook
Generated via openpyxl at outputs/workbook.xlsx containing 8 sheets structured in exact sequence:
1. README: Project identity, calendar specifications, synthetic disclaimer, parameter declarations, and formula documentation.
2. Schedule: 38 project activities with CPM early/late schedules, total float, criticality flags, and baseline vs forecast calendar dates.
3. BOQ_Budget: 13 work item lines with quantity, unit rates, and dynamic Excel formulas =D{r}*E{r} for item amounts, terminating in a =SUM(F2:F14) total row matching BAC (INR 38,113,500).
4. Monthly_EVM: Cumulative monthly EVM table (rows 2 to 7 for months 1 to 6) with values for Month, PV, EV, and AC, accompanied by live Excel formulas for all derived metrics:
   - Schedule Variance (col E): =C{r}-B{r}
   - Cost Variance (col F): =C{r}-D{r}
   - Schedule Performance Index (col G): =IF(B{r}=0,"",C{r}/B{r})
   - Cost Performance Index (col H): =IF(D{r}=0,"",C{r}/D{r})
   - Estimate at Completion (col I): =IF(H{r}="",$N$1,$N$1/H{r}) referencing BAC at cell $N$1
   - Estimate to Complete (col J): =I{r}-D{r}
   - Variance at Completion (col K): =$N$1-I{r}
   - To-Complete Performance Index (col L): =IF($N$1-D{r}=0,"",($N$1-C{r})/($N$1-D{r}))
5. Flags: Full cross-month warning register with month, rule category, severity, magnitude, root-cause reason, owner, and action text.
6. Materials: Month-6 stock ledger and Month-7 forward procurement plan.
7. RA_Bills: Monthly contractor billing register (RA-01 to RA-06) with dynamic Net Payable formulas =C{r}-F{r}-G{r} (Gross - Retention - TDS).
8. QC_Log: Chronological quality inspection logs and non-conformance records.

All data worksheets implement freeze panes below header rows (A2), clear gridlines, auto-fitted column widths, and standardized formatting (#,##0 for currency, 0.000 for performance indices, yyyy-mm-dd for calendar dates). Date fields across Schedule, RA_Bills, QC_Log, and Flags are stored as native date objects.

### 10.3 1-Page Report for the Regional Project Head (PDF)
Generated via ReportLab at outputs/report_month_06.pdf, designed to fit a single A4 portrait page (595.27 pt x 841.89 pt) without visual truncation or page overflow across months 1, 3, and 6:
- Header & Authority: Document title, reporting period, project metadata, data date, and distribution to Regional Project Head.
- Status Banner: Overall status color dot (Red/Amber/Green) with summary commentary on handover forecast and core index drivers.
- Visual S-Curve: Embedded compact vector-style chart rendering baseline planned value against cumulative earned value and actual cost.
- Key EVM Metrics Matrix: Two-row non-overlapping comparative scorecard presenting Cost KPIs (PV, EV, AC, SV, CV, EAC, VAC) in Row 1 and Schedule KPIs (SPI, CPI, TCPI, EAC Combined, Baseline Handover, Forecast Handover, Delay) in Row 2.
- Top 5 Issues Register: Prioritized actionable table displaying severity dots, activity location (with wide "Where" column preventing line wrap), diagnosis, owner, and prescribed mitigation.
- Milestone Tracking Table: Planned vs forecast delivery dates, working-day slippage, and explicit Status column (Achieved with actual date for completed milestones, Forecast for future milestones).
- Next-Month Material Plan: Quantitative purchase requirements with human-readable labels (Cement, bags, Steel, kg, Sand, cum, Aggregate, cum, Bricks, nos) formatted with integer counts for bags/bricks and "-" for zero values.
- Financial & Quality Exceptions: Split summary detailing pending/held RA bills (identifying RA-05 hold reason) and open structural NCRs (tracking NCR-003 ageing and reading non-conformance detail directly from config without invented numbers).
- Operational & Financial Drivers: Dedicated summary commentary box synthesizing schedule delay root causes, cost escalation drivers, material shortfall history, and cumulative contractor retention.
- Compliance & Localization: Indian digit grouping (format_inr, e.g., Rs 1,87,43,829), explicit Rs prefix, standardized date format ("18 Sep 2026"), and synthetic origin watermark.

### 10.4 Interactive Streamlit Dashboard (app.py)
Built with Streamlit (streamlit run app.py) in wide layout, structured with cached data loaders (@st.cache_data) for responsive real-time exploration across project months 1 to 6. The dashboard features:
- Sidebar Controls: Dynamic month selector slider (1 to 6), project metadata, data date indicator, and persistent synthetic data caption.
- Seven Structured Tabs:
  1. Overview: High-visibility status banner with PDF-matched status text, KPI metric cards (SPI, CPI, EAC, VAC, forecast handover with delay indicator), warning flag counts by severity, top 5 priority issues table, and an expandable full flags register filterable by category.
  2. Schedule & Critical Path: High-resolution Gantt comparison image (baseline outline vs forecast filled bars, with critical path highlighted in red), milestone tracking table (baseline vs forecast vs slip), CPM network schedule table with a "critical path only" toggle, and the critical path activity sequence.
  3. Cost & EVM: Monthly S-curve chart through month m, cumulative EVM performance history table (months 1..m), activity-level cost and variance table for month m, BOQ item cost variance table, what-if sensitivity dual-table section, and methodology notes comparing standard EAC (BAC / CPI) against conservative combined EAC_combined.
  4. Materials: Month-m stock inventory status ledger, forward month-m+1 purchase plan, and an interactive baseline material consumption bar chart with material selector.
  5. Payments: Contractor RA bills register at month-end data date, cumulative retention held metric, and payment warning flags.
  6. Quality: Quality inspection ledger filterable by result (All, Pass, Fail), non-conformance report (NCR) register, and headline quality metrics (total inspections, pass rate, open NCRs, average closure time).
  7. Monthly Report: Download interface providing one-click generation and retrieval of the 1-page report for the Regional Project Head and multi-sheet Excel workbook.

---

## 11. Verification and Independent Validation

### 11.1 Independent Cross-Check Implementation (tests/test_cross_check.py)
To prevent regression and verify numerical results, the project implements an independent verification module completely decoupled from production scheduling and EVM code:
1. CPM by Repeated Relaxation: Rather than relying on network topological sorting or pandas DataFrames, early and late event times are computed using a plain iterative relaxation loop over raw predecessor dictionaries until convergence. Total float and critical activities are derived directly (TF = LF - EF). The test asserts that Early Start, Early Finish, Late Start, Late Finish, and Total Float match compute_cpm exactly across all 38 activities for both baseline and actual schedules.
2. Day-by-Day Calendar Walk: Calendar month boundaries and working days are independently validated using standard library datetime.date and calendar modules, walking day by day from project commencement (2026-01-05) and skipping Sundays. The resulting working-day counts for months 1 to 9 match month_end_wd exactly.
3. First-Principles EVM Recomputation: Planned Value (PV), Earned Value (EV), and Actual Cost (AC) for months 1 to 6 are recomputed from first principles using standard loops over raw CSV and YAML data:
   - Budget per activity derived directly from BOQ share x quantity x rate.
   - Linear daily expenditure spread over planned durations.
   - Physical percent complete calculated as days worked divided by actual duration (19 wd on SLAB_F2).
   - Actual costs recomputed using placed quantities, baseline rates, non-critical cost noise, and the month-3 steel rate escalation (+10%).
   The test verifies that PV and EV match within INR 1.00, AC matches within INR 1.00, and Month 6 performance indices (SPI, CPI, EAC, TCPI) match within 1e-9.

### 11.2 Number Tracing and Consistency Protocol (scripts/check_numbers.py)
To eliminate discrepancies and untraced figures across deliverables:
1. Source of Truth Aggregation: A full dictionary of authorized numeric representations is harvested recursively from outputs/results.json, config/project.yaml, and outputs/test_summary.json. Each number is expanded into all permissible formatting permutations (raw integers/floats, 0/1/2/3 decimal places, Indian comma grouping, standard Western grouping, percentage format, currency prefixes Rs, and multi-format calendar date strings like YYYY-MM-DD, DD Mon YYYY, D Mon YYYY).
2. Structural Allow-List: A documented allow-list accommodates structural constants: building configuration ("G+4", "400", "2000", "5"), paper standards ("A4"), month indices (1 to 12), and calendar year ("2026").
3. Automated Audit: scripts/check_numbers.py extracts all rendered text from outputs/report_month_06.pdf, README.md, and docs/INTERVIEW_NOTES.md, tokenizes numeric entities while properly ignoring alphanumeric codes (e.g., SLAB_F2, NCR-003, RA-05, M25, Fe500), and verifies that every single number maps to an authorized value. If any unauthorized number is detected, the script reports the number with its surrounding context and exits with status 1.

### 11.3 What-If Sensitivity Analysis Framework (src/sensitivity.py)
A systematic multi-parameter sensitivity analysis evaluates project financial and schedule resilience against varying operational disruptions without modifying persistent configuration files:
1. Steel Price Escalation Scan: Evaluates steel rate uplifts of 5%, 10%, and 15% from Month 3 onwards, while holding the second-floor slab delay constant at 10 working days. Because physical progress and activity durations are invariant to material costs, SPI (0.825) and forecast handover date (2026-09-18, +10 wd) remain unchanged. Concurrently, increasing steel escalation drives CPI downward (0.988 to 0.977 to 0.966), escalating EAC monotonically (Rs 3,85,78,519 to Rs 3,90,26,515 to Rs 3,94,74,512) and widening cost variance at completion (VAC).
2. Structural Slab Delay Scan: Evaluates critical-path schedule delays on SLAB_F2 across 5, 10, and 15 working days, holding steel escalation constant at 10%. Because SLAB_F2 is critical (TF = 0), any delay of N working days transfers directly to the critical path, resulting in a forecast project handover delay of exactly N working days (2026-09-12 for +5 wd, 2026-09-18 for +10 wd, and 2026-09-24 for +15 wd).
3. In-Memory Configuration Overrides: Sensitivity simulations are executed via pipeline.run(config_overrides=..., export_outputs=False) using deep dictionary updates on in-memory configuration structures, keeping config/project.yaml unmodified during execution. Results are serialized to outputs/sensitivity.json and included in results.json and the Streamlit Cost & EVM tab.
