# REG-US-BSA-CTR · Bank Secrecy Act — Currency Transaction Report

**Document ID:** REG-US-BSA-CTR-v1
**Jurisdiction:** US
**Regulator:** FinCEN (Financial Crimes Enforcement Network)
**Primary Source:** 31 CFR §1010.311, §1010.313; FinCEN Form 112 (CTR)
**Advisory Reference:** FIN-2012-A002 (Funnel Accounts)
**Source Type:** external_regulatory
**Rule Nexus:** R168 (Cash Structuring), R181 (Rapid Movement / Funnel)

---

## 1. Reporting Threshold

A financial institution must file a Currency Transaction Report (**CTR / FinCEN Form 112**) for every cash transaction in currency of **more than USD 10,000** conducted by, through, or to the institution on any single business day. Multiple related transactions are **aggregated** if the institution knows they are by or on behalf of the same person and total more than USD 10,000.

**Threshold:** USD 10,000.01 and above.
**Aggregation window:** one business day.

## 2. Structuring — Statutory Definition

Under **31 USC §5324**, it is unlawful for any person to structure, or attempt to structure, or assist in structuring, any transaction with one or more domestic financial institutions for the purpose of evading the CTR reporting requirement. This applies whether or not the individual transaction is itself lawful.

**Detection nexus:** Rule R168 (round-denomination structuring, band USD 8,500 – 9,999) is calibrated to sit just below the CTR trigger and above typical retail cash activity.

## 3. Funnel Account Indicators (FIN-2012-A002)

FinCEN advises institutions to monitor for **funnel accounts** — accounts that receive numerous cash deposits, often in amounts below the CTR threshold, in a geographic area distinct from the account holder's location, followed by rapid outbound transfers.

**Red flags relevant to R181:**
- Multiple cash deposits in different branches or ATMs within a short window.
- Rapid outbound wire, ACH, or peer-to-peer transfer within 24–72 hours.
- Deposits sized to avoid CTR/SAR thresholds.

## 4. Suspicious Activity Report (SAR) Nexus

Where structuring is suspected, the institution must file a **SAR (FinCEN Form 111)** within 30 calendar days of initial detection (60 if no suspect identified). SAR filing is required **independent** of CTR filing.

## 5. Recordkeeping

CTRs and supporting records must be retained for **five years**. Aggregation logic must be auditable — if a monitoring system triggers on aggregated cash activity, the evidence packet must show which underlying transactions contributed.
