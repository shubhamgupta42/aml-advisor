# REG-DE-BAFIN-AUA · Germany BaFin — Auslegungs- und Anwendungshinweise (AuA)

**Document ID:** REG-DE-BAFIN-AUA-v1
**Jurisdiction:** DE
**Regulator:** BaFin (Bundesanstalt für Finanzdienstleistungsaufsicht)
**Primary Source:** GwG (Geldwäschegesetz) §10, §15; BaFin AuA — General Part & Special Part for Credit Institutions
**Related:** EU 4th/5th/6th AMLD; upcoming AMLR / AMLA (2027)
**Source Type:** external_regulatory
**Rule Nexus:** R168, R174

---

## 1. Cash Transaction Thresholds

Under **§10(3) GwG**, enhanced customer due diligence applies to cash transactions of **EUR 10,000 or more** in a single transaction or linked series. For real estate and precious-metals dealers, the threshold is **EUR 2,000**.

**Implication:** R168 (structuring) in a German deployment is calibrated against the EUR 10,000 trigger, not USD 10,000 — the FX-adjusted band is configured via the Rule Catalog's `country_overrides.DE` block.

## 2. Enhanced Due Diligence (EDD)

**§15 GwG** requires EDD for high-risk situations: PEPs, high-risk third countries (per EU Commission delegated regulation), correspondent banking with third-country respondents, and complex or unusually large transactions with no apparent economic purpose.

**Cross-border nexus (R174):** payments to/from EU-designated high-risk third countries trigger EDD irrespective of amount. This is one of the reasons the cross-border-layering rule cannot be a pure amount threshold — RTCA carries the jurisdiction risk tiers.

## 3. Suspicious Transaction Reporting

Institutions must file a **Verdachtsmeldung (STR)** with the **FIU Deutschland** (Financial Intelligence Unit, hosted at Zoll) immediately upon suspicion. The reporting standard is *suspicion*, not proof — mirroring the UK model, unlike the US CTR threshold model.

## 4. Transaction Monitoring Systems

BaFin's AuA General Part §5.2 requires **automated monitoring systems** proportionate to the institution's risk profile. Systems must be:
- Regularly recalibrated (typically annually, or on material business change).
- Backtested against confirmed SAR outcomes.
- Documented in a way auditable by BaFin inspectors.

**MDD nexus:** the calibration-history section in each MDD is what an auditor asks for.

## 5. Record Retention

**Five years** minimum under §8 GwG; ten years for tax purposes under §147 AO where applicable.
