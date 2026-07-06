# MDD-003 · Rapid Movement of Funds (Pass-Through Activity)

**Document ID:** MDD-003-RAPIDMOVE-v1.5
**Typology:** Rapid Movement of Funds — Pass-Through / Funnel Account
**Owner:** AFC Methodology Team
**Status:** APPROVED
**Last Calibration:** 2026-Q1
**Next Review:** 2026-Q4

---

## 1. Purpose & Scope

This MDD specifies the detection logic for the **Rapid Movement of Funds** scenario, deployed as rule **R181** in Production. The scenario targets the **layering** stage of money laundering, in which funds are deposited and quickly moved out of an account — leaving little or no residual balance — to disguise the audit trail (FATF Money Laundering Stages Typology, 2020; BIS WG Report 2021 on Funnel Accounts).

**In-scope products:** All Demand-Deposit Accounts (DDA), Corporate Cash Management (CCM).
**Out-of-scope products:** Treasury / Money Market accounts (covered separately by MDD-008).

---

## 2. RTCA Coverage Mapping

| Country | RTCA Risk Tier | Rule Active | Pass-Through Window | Min Notional (USD-eq.) |
|---|---|---|---|---|
| US | Tier 1 | YES | 48h | 5,000 |
| UK | Tier 1 | YES | 48h | 5,000 |
| DE | Tier 1 | YES | 48h | 5,000 |
| SG | Tier 2 | YES | 72h | 5,000 |
| IN | Tier 2 | YES | 72h | 3,000 |
| AE | Tier 2 | YES | 72h | 5,000 |
| JP | Tier 3 | NO  | n/a | n/a — covered by `LR-JP-019` |

The rule is registered as an **ECL Rule** with per-country window and notional. Country-specific parameters are recorded in the Rule Catalog under `country_overrides`.

---

## 3. Customer Scope

The rule applies to all DDA / CCM customer segments **except**:

- Treasury sweep accounts (intentional same-day in-out by design).
- Escrow accounts (`ACCOUNT_TYPE = ESCROW`).
- Settlement accounts of regulated broker-dealers (pre-flagged in Customer Master).
- Customers with an active Cash-Pooling exemption granted by Corporate Treasury.

---

## 4. Detection Logic (Truth-of-Rule)

The scenario fires when **all** conditions are met within the **Pass-Through Window** (see §2):

1. The account receives a credit transaction of amount ≥ **Min Notional**
2. Within the Pass-Through Window, ≥ **70%** of that credit amount is debited from the account
3. Across **N ≥ 2** distinct outbound counterparties (multi-leg fan-out)
4. End-of-window residual balance is < **10%** of the original credit
5. The pattern repeats on **≥ 2 distinct days** within a rolling **30-day** window (pattern reinforcement)

### 4.1 Key Data Elements (KDEs)

| KDE | Source System | Type |
|---|---|---|
| `customer_id` | Customer Master (Hub) | str |
| `txn_amount_usd` | Transaction Hub | float |
| `txn_direction` | Transaction Hub | enum {CREDIT, DEBIT} |
| `counterparty_id` | Transaction Hub | str |
| `account_balance_eod` | Account Ledger (end-of-day) | float |
| `account_type` | Customer Master | enum |

### 4.2 Pattern Reinforcement

The **2-day requirement** (condition §4.5) was added in v1.3 specifically to suppress single-occurrence false positives — e.g. a small business making a one-off large payment-out the day after a customer settlement. Confirmed funnel-account schemes almost always show the pass-through pattern on multiple days.

---

## 5. Threshold Calibration Rationale

The **70% debit ratio** and **10% residual** thresholds were chosen because:

- BIS Funnel-Account Study (2021) found 89% of confirmed funnel accounts emptied ≥ 75% of credits within 72h
- A 50% debit ratio over-fired on normal payroll-then-rent-then-utilities patterns (FP rate 51% in pilot)
- A 90% debit ratio missed 14% of confirmed cases that retained small balances as cover

The **2-counterparty fan-out** distinguishes layering (multiple outbound legs) from simple sweep activity (single outbound).

---

## 6. Calibration History

| Version | Date | Change | Reason | Approver |
|---|---|---|---|---|
| v1.0 | 2024-01 | Initial deployment | New RTCA-2024 coverage for layering stage | MLRO |
| v1.1 | 2024-05 | Min Notional $3k → $5k (Tier-1 countries) | Tier-1 FP rate 44% with $3k floor | AFC Lead |
| v1.2 | 2024-09 | Added §3 escrow / treasury-sweep carve-outs | Treasury escalations | MLRO |
| v1.3 | 2025-Q2 | Added 2-day pattern reinforcement (§4.5) | Single-day pattern alone produced 38% FP | MLRO |
| v1.4 | 2025-Q4 | India notional $5k → $3k | India FIU advisory on micro-layering | MLRO |
| v1.5 | 2026-Q1 | RTCA refresh; AE Tier reclassification | RTCA-2026 update | Head of FC |

---

## 7. Sensitivity Analysis

2025-Q4 sweep, 18-month sample (2.1M alerts, 1,847 confirmed SARs).

| Parameter | Baseline | -20% | +20% | Selected |
|---|---|---|---|---|
| Debit ratio | 70% | 56% (recall +4%, FP +29%) | 84% (recall -11%, FP -18%) | **70%** |
| Pass-through window | 48h | 38h (recall -13%, FP -22%) | 58h (recall +5%, FP +19%) | **48h (Tier-1) / 72h (Tier-2)** |
| Residual ceiling | 10% | 8% (recall -2%, FP -8%) | 12% (recall +1%, FP +11%) | **10%** |
| Counterparty min | 2 | 1 (recall +9%, FP +52%) | 3 (recall -16%, FP -27%) | **2** |

---

## 8. Known Edge Cases / False-Positive Patterns

1. **Property closings / large purchases** — legitimate one-day large in/out. Suppressed by the 2-day reinforcement rule (§4.5).
2. **Payroll processing accounts** at small businesses — credit-then-distribute. These are typically flagged in Customer Master with `CIB-MEDIUM` and routed to a separate MDD overlay.
3. **Crypto on-ramp / off-ramp accounts** at licensed VASPs — high volume, fast turnover by design. Pre-flagged with `ACCOUNT_TYPE = VASP_FIDUCIARY`.
4. **Charity disaster-response accounts** during active appeals — manual review path with SAR Decision Tree §8.2.

---

## 9. Approvals & Sign-Off

| Role | Name | Date | Signature |
|---|---|---|---|
| Methodology Author | [redacted] | 2026-01-11 | ✓ |
| AFC Lead | [redacted] | 2026-01-15 | ✓ |
| MLRO | [redacted] | 2026-01-21 | ✓ |
| Head of Financial Crime | [redacted] | 2026-01-26 | ✓ |

---

## 10. Related Documents

- Rule Catalog entry: `R181` (active in 6 countries; see §2)
- RTCA-2026 §5.1 (Layering / Rapid Movement coverage)
- MDD-001-STRUCTURING (often co-fires for cash funnels)
- MDD-002-CROSSBORDER (cross-border layering overlay)
- BIS Funnel-Account Study 2021 (external reference)
- SAR Decision Tree §8 (rapid-movement escalation paths)
