# MDD-002 · Cross-Border Funds Movement (High-Risk Corridor)

**Document ID:** MDD-002-CROSSBORDER-v2.4
**Typology:** Cross-Border Funds Movement — High-Risk Corridor
**Owner:** AFC Methodology Team
**Status:** APPROVED
**Last Calibration:** 2026-Q1
**Next Review:** 2026-Q3

---

## 1. Purpose & Scope

This MDD specifies the detection logic for the **Cross-Border High-Risk Corridor** scenario, deployed as rule **R174** in Production. The scenario targets layering activity in which funds are moved internationally to or from jurisdictions of elevated AML risk, in patterns inconsistent with the customer's known economic profile (FATF Recommendation 13; Wolfsberg Cross-Border Payments Guidance 2022).

**In-scope products:** Corporate Cash Management (CCM), Retail Wire Transfers.
**Out-of-scope products:** Trade Finance (covered by MDD-005-TFL), Securities Services.

---

## 2. RTCA Coverage Mapping

| Country (Originating) | RTCA Risk Tier | Rule Active | Local Threshold (USD-eq.) | Notes |
|---|---|---|---|---|
| US | Tier 1 | YES | 15,000 | OFAC + FinCEN 314(a) overlay |
| UK | Tier 1 | YES | 12,000 | FCA SYSC + JMLSG Part II |
| DE | Tier 1 | YES | 12,000 | BaFin AuA + EU AMLD6 |
| SG | Tier 2 | YES | 15,000 | MAS PSN01 |
| IN | Tier 2 | YES | 7,500  | RBI MD + LRS scrutiny; **NRE/NRO accounts have special carve-out — see §3** |
| AE | Tier 2 | YES | 15,000 | CBUAE + UAE PNS |
| JP | Tier 3 | YES | 20,000 | JAFIC |

The **High-Risk Corridor** definition follows the FATF "Increased Monitoring" list plus the bank-internal Country Risk Catalog (CRC-2026). Both lists are refreshed quarterly.

The rule is registered as an **ECL Rule** with per-corridor parameters (see §4.2).

---

## 3. Customer Scope

The rule applies to all customer segments **except**:

- **NRE / NRO account holders** (Indian residents abroad) — these accounts have legitimate cross-border flows; covered by a separate local rule `LR-IN-NRE-014` with a higher threshold and additional KYC fields.
- Multinational corporates with a **Treasury-Centre exemption** flag granted by the Corporate Onboarding team.
- Inter-bank settlement (`NOSTRO`/`VOSTRO`).
- Customers under active EDD with documented expected-flow corridors.

---

## 4. Detection Logic (Truth-of-Rule)

The scenario fires when **all** conditions are met within the **Lookback Period of 30 calendar days**:

1. The customer initiated **N ≥ 2** outbound (or inbound) wire transfers
2. At least one counterparty is in a **High-Risk Corridor** country (FATF Increased-Monitoring list ∪ CRC-2026 Tier-3 ∪ Tier-4)
3. The cumulative cross-border amount exceeds the country-specific threshold (see §2)
4. The activity is **inconsistent** with the customer's declared expected monthly cross-border volume (`expected_xb_volume_usd` field from KYC), measured as `cumulative > 3 × expected`
5. The customer is **not** in the carve-outs listed in §3

### 4.1 Key Data Elements (KDEs)

| KDE | Source System | Type |
|---|---|---|
| `customer_id` | Customer Master (Hub) | str |
| `txn_amount_usd` | Transaction Hub (FX-normalized) | float |
| `originating_country` | SWIFT MT103 field 50K / BIC routing | str |
| `beneficiary_country` | SWIFT MT103 field 59 / BIC routing | str |
| `corridor_risk_tier` | Country Risk Catalog (CRC-2026) | enum |
| `expected_xb_volume_usd` | KYC Master (refreshed annually) | float |
| `account_type` | Customer Master | enum |

### 4.2 Per-Corridor Parameters

| Corridor (Originating → Beneficiary) | Threshold (USD-eq.) | Lookback | Justification |
|---|---|---|---|
| Any Tier-1 → Tier-4 | 7,500 | 30d | Tightest — destination is sanctioned-proximate |
| Any Tier-1 → Tier-3 | 12,000 | 30d | Baseline |
| Tier-2 → Tier-3 | 12,000 | 30d | Baseline |
| Tier-2 → Tier-4 | 7,500 | 30d | Tightened |
| Tier-3 → Tier-3 | 20,000 | 30d | Higher floor — many legitimate corridor pairs |

---

## 5. Threshold Calibration Rationale

The 30-day Lookback was chosen because:

- Layering schemes typically execute within a **rolling month**, after which the funds are integrated into the destination economy
- 7-day lookback misses 22% of confirmed cross-border SARs (2024 retro analysis)
- 60-day lookback adds only +1.5% recall but increases FP rate by 41%

The `3 × expected` multiplier comes from the 2024 Customer Behavior Study: legitimate fluctuations rarely exceed 2.5× declared expected volume; the 3× floor provides a safety margin while still catching layering.

---

## 6. Calibration History

| Version | Date | Change | Reason | Approver |
|---|---|---|---|---|
| v1.0 | 2023-06 | Initial deployment | New corridor risk under RTCA-2023 | MLRO |
| v2.0 | 2024-04 | Added per-corridor parameter table (§4.2) | Single flat threshold over-fired in Tier-3→Tier-3 corridors | MLRO |
| v2.1 | 2024-10 | NRE/NRO carve-out (§3) | Investigator feedback: legitimate flows flagged | AFC Lead |
| v2.3 | 2025-Q4 | `3 × expected` multiplier introduced | 2024 Customer Behavior Study finding | MLRO |
| v2.4 | 2026-Q1 | CRC refresh; added 2 Tier-4 countries | CRC-2026 update | Head of FC |

---

## 7. Sensitivity Analysis

2025-Q4 sweep on 14-month sample (1.2M alerts, 2,108 confirmed SARs).

| Parameter | Baseline | -20% | +20% | Selected |
|---|---|---|---|---|
| Lookback | 30d | 24d (recall -9%, FP -27%) | 36d (recall +2%, FP +18%) | **30d** |
| Expected-multiplier | 3× | 2.4× (recall +6%, FP +35%) | 3.6× (recall -8%, FP -22%) | **3×** |
| N minimum | 2 | 1 (recall +12%, FP +84%) | 3 (recall -18%, FP -41%) | **2** |
| Tier-1→Tier-3 floor | $12k | $9.6k (recall +3%, FP +17%) | $14.4k (recall -5%, FP -14%) | **$12k** |

---

## 8. Known Edge Cases / False-Positive Patterns

1. **Education remittances** — students abroad receiving regular family transfers. Mitigated by NRE/NRO carve-out (§3) where applicable.
2. **Diplomatic accounts** — legitimate high-volume Tier-1→Tier-4 flows. These accounts are pre-flagged in Customer Master with `ACCOUNT_TYPE = DIPLOMATIC` and bypass the rule.
3. **Charity / NGO accounts** active in conflict zones — manual review path documented in SAR Decision Tree §6.3.
4. **Customer-declared trade flows** that legitimately exceed the multiplier — investigator can refresh `expected_xb_volume_usd` via the KYC Refresh workflow.

---

## 9. Approvals & Sign-Off

| Role | Name | Date | Signature |
|---|---|---|---|
| Methodology Author | [redacted] | 2026-01-09 | ✓ |
| AFC Lead | [redacted] | 2026-01-12 | ✓ |
| MLRO | [redacted] | 2026-01-19 | ✓ |
| Head of Financial Crime | [redacted] | 2026-01-25 | ✓ |

---

## 10. Related Documents

- Rule Catalog entry: `R174` (active in 7 countries; see §2)
- Country Risk Catalog: `CRC-2026`
- RTCA-2026 §4.2 (Cross-Border Layering coverage)
- MDD-001-STRUCTURING (related — domestic structuring)
- MDD-005-TFL (Trade-finance overlap, when corridor activity is trade-backed)
- SAR Decision Tree §6 (cross-border escalation paths)
