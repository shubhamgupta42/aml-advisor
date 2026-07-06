# REG-JP-JAFIC · Japan JAFIC / FSA — AML/CFT Guidance

**Document ID:** REG-JP-JAFIC-v1
**Jurisdiction:** JP
**Regulator:** FSA (Financial Services Agency); JAFIC (Japan Financial Intelligence Center, National Police Agency)
**Primary Source:** Act on Prevention of Transfer of Criminal Proceeds (APTCP); FSA "Guidelines for AML/CFT" (2018, amended 2021)
**Source Type:** external_regulatory
**Rule Nexus:** R168, R174

---

## 1. Suspicious Transaction Reporting

Under **APTCP Article 8**, specified business operators (including banks) must file a **Suspicious Transaction Report (STR)** with **JAFIC** promptly upon suspicion. No monetary threshold.

## 2. Cash Transaction Verification

APTCP requires enhanced customer verification for cash transactions of **JPY 2,000,000 or more** (roughly USD 13,000 depending on FX). This is a **verification** threshold, not a filing threshold.

**R168 nexus (Japan):** the structuring rule in JP deployments is calibrated against JPY, with the country override captured in the Rule Catalog.

## 3. FSA Risk-Based Approach Guidelines

The FSA's 2018 guidelines (with subsequent amendments) instruct institutions to adopt a **risk-based approach**, including:
- Enterprise-wide risk assessment refreshed at least annually.
- Customer risk categorisation with defined CDD depth per category.
- Ongoing transaction monitoring with recalibrated thresholds.

**MDD calibration-history nexus:** the annual recalibration expectation is what makes the MDD's §6 Calibration History a required audit artefact.

## 4. Cross-Border Wire Transfers

For wire transfers, originator and beneficiary information must accompany the transfer per FATF Recommendation 16, implemented via APTCP and FSA guidance. Incomplete-information transfers must be identified and handled per the institution's policy.

## 5. Record Retention

**Seven years** for transaction records under APTCP — longer than the five-year minimum common in other jurisdictions. Systems must retain alert evidence packets accordingly.
