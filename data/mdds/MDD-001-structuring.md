# MDD-001 · Cash Structuring (Round-Denomination)

**Document ID:** MDD-001-STRUCT-v3.2
**Typology:** Cash Structuring — Round-Denomination
**Owner:** AFC Methodology Team
**Status:** APPROVED
**Last Calibration:** 2026-Q1
**Next Review:** 2026-Q4

---

## 1. Purpose & Scope

This Methodology Design Document specifies the detection logic, threshold calibration, and operational parameters for the **Round-Denomination Cash Structuring** scenario, deployed as rule **R168** in the Production Transaction Monitoring system.

The scenario targets the **structuring** typology (FATF Glossary, 2014; FinCEN Advisory FIN-2012-A002), in which a customer deliberately breaks a single cash transaction into multiple smaller deposits to stay below a regulatory reporting threshold — most commonly the US Bank Secrecy Act's USD 10,000 Currency Transaction Report (CTR) trigger.

**In-scope products:** Corporate Cash Management (CCM), Retail Demand-Deposit Accounts.
**Out-of-scope products:** Trade Finance & Lending, Securities Services, Investment Banking.

---

## 2. RTCA Coverage Mapping

| Country | RTCA Risk Tier | Rule Active | Local Threshold (USD-eq.) | Notes |
|---|---|---|---|---|
| US | Tier 1 | YES | 9,500 | BSA CTR trigger at 10,000 |
| UK | Tier 1 | YES | 9,500 | FCA SYSC 6.3 |
| DE | Tier 1 | YES | 9,500 | BaFin AuA |
| SG | Tier 2 | YES | 9,500 | MAS Notice 626 |
| IN | Tier 2 | YES | 9,500 | RBI MD on KYC |
| AE | Tier 2 | YES | 9,500 | CBUAE AML Guidance |
| JP | Tier 3 | NO  | n/a  | Covered by local rule LR-JP-027 |

The rule is registered as an **ECL Rule** (Enterprise-Coverage Layer) — global by default, with the per-country threshold above. Country-specific exceptions are tracked in the Rule Catalog under `country_overrides`.

---

## 3. Customer Scope

The rule applies to all customer segments **except**:

- Cash-intensive businesses pre-classified as `CIB-HIGH` in the Customer Master (e.g. licensed money-services businesses, casinos, registered cash-handlers) — these have a dedicated MDD (MDD-007-CIB).
- Customers with an active Enhanced Due Diligence (EDD) exemption flag granted by the Sanctions & Embargoes team.
- Inter-bank settlement accounts (`ACCOUNT_TYPE = NOSTRO` or `VOSTRO`).

---

## 4. Detection Logic (Truth-of-Rule)

The scenario fires when **all** of the following conditions are met within the **Lookback Period** of **5 calendar days**:

1. The customer initiated **N ≥ 3** cash credit transactions
2. Each transaction amount falls in the band `[USD 8,500 , USD 9,999]` (the structuring "sweet spot")
3. The cumulative sum across N transactions exceeds **USD 25,000**
4. At least **2** of the N transactions are in a **round-denomination** pattern — defined as amounts ending in `00` or `50` (e.g. `$9,500`, `$9,900`)
5. The transactions span **≥ 2 distinct booking locations** (branch / ATM / channel)

### 4.1 Key Data Elements (KDEs)

| KDE | Source System | Type |
|---|---|---|
| `customer_id` | Customer Master (Hub) | str |
| `txn_amount_usd` | Transaction Hub (post-FX normalization) | float |
| `txn_currency` | Transaction Hub | str |
| `txn_channel` | Transaction Hub | enum {BRANCH, ATM, ONLINE, MOBILE, AGENT} |
| `txn_date` | Transaction Hub | date |
| `booking_location_id` | Branch Master | str |
| `is_round_denomination` | Derived (KDE-Lab) | bool |

---

## 5. Threshold Calibration Rationale

The threshold band `[$8,500 , $9,999]` was selected because:

1. The US BSA CTR reporting trigger is **$10,000**. Structurers stay just below.
2. Field studies (FinCEN SAR Stats 2018–2023) show **94% of confirmed structuring SARs** had at least one transaction in `[$8,500 , $9,999]`.
3. Tightening the lower bound to $9,000 reduced false-positive rate by 18% in the 2025-Q4 sensitivity analysis but missed 6% of confirmed SARs — judged not worth the event-loss trade-off.

The N ≥ 3 minimum was set after sensitivity analysis (see §7); N=2 produced excessive false positives on legitimate biweekly cash deposits.

---

## 6. Calibration History

| Version | Date | Change | Reason | Approver |
|---|---|---|---|---|
| v1.0 | 2023-03 | Initial deployment | New typology coverage requirement (RTCA-2023) | MLRO |
| v2.0 | 2024-02 | Lookback 7d → 5d; N threshold 2 → 3 | Q4-2023 tuning report: FP rate 38% | MLRO |
| v2.1 | 2024-08 | Added `is_round_denomination` KDE | Investigator feedback: missing pattern | AFC Lead |
| v3.0 | 2025-Q4 | Added booking-location dispersion requirement | Sensitivity analysis — geo dispersion is a strong SAR signal | MLRO |
| v3.2 | 2026-Q1 | RTCA refresh; added IN, AE | RTCA-2026 expansion | Head of FC |

---

## 7. Sensitivity Analysis

The 2025-Q4 calibration ran the following sensitivity sweeps on a held-out 2024 sample (12 months, 850k alerts, 1,240 confirmed SARs).

| Parameter | Baseline | -20% | +20% | Selected |
|---|---|---|---|---|
| Lower band | $8,500 | $8,000 (recall +2%, FP +14%) | $9,000 (recall -6%, FP -18%) | **$8,500** |
| Lookback | 5d | 4d (recall -8%, FP -22%) | 7d (recall +3%, FP +31%) | **5d** |
| N minimum | 3 | 2 (recall +5%, FP +47%) | 4 (recall -11%, FP -19%) | **3** |
| Cumsum floor | $25k | $20k (recall +2%, FP +9%) | $30k (recall -7%, FP -12%) | **$25k** |

---

## 8. Known Edge Cases / False-Positive Patterns

1. **Payroll cycle** — corporate accounts that pay daily-wage workers in cash often trigger N≥3 in `[$8,500, $9,999]` legitimately. Mitigated by the round-denomination requirement (payroll is rarely round).
2. **Property closing** — real-estate transactions with multiple sub-payments. Investigators have escalation guidance in the SAR Decision Tree §4.7.
3. **Festival / holiday seasons** — Diwali, Chinese New Year. Calibration is **not** seasonally adjusted; investigators apply judgement.

---

## 9. Approvals & Sign-Off

| Role | Name | Date | Signature |
|---|---|---|---|
| Methodology Author | [redacted] | 2026-01-14 | ✓ |
| AFC Lead | [redacted] | 2026-01-18 | ✓ |
| MLRO | [redacted] | 2026-01-22 | ✓ |
| Head of Financial Crime | [redacted] | 2026-01-28 | ✓ |

---

## 10. Related Documents

- Rule Catalog entry: `R168` (active in 6 countries; see §2)
- RTCA-2026 §3.1 (Structuring coverage)
- MDD-002-CROSSBORDER (related typology)
- MDD-007-CIB (carve-out for cash-intensive businesses)
- SAR Decision Tree §4 (investigator escalation paths)
