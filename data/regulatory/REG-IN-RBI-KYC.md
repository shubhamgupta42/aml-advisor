# REG-IN-RBI-KYC · India RBI — Master Direction on KYC / AML

**Document ID:** REG-IN-RBI-KYC-v1
**Jurisdiction:** IN
**Regulator:** RBI (Reserve Bank of India)
**Primary Source:** RBI Master Direction — Know Your Customer (KYC) Direction, 2016 (as amended)
**Related Legislation:** PMLA 2002 (Prevention of Money Laundering Act); PMLA Rules 2005
**Source Type:** external_regulatory
**Rule Nexus:** R168, R174, R181

---

## 1. Cash Transaction Reporting (CTR)

Under **PMLA Rule 3**, regulated entities must report to **FIU-IND**:
- All **cash transactions of INR 10 lakh (1,000,000)** and above, or their FX equivalent, in a month.
- All series of cash transactions integrally connected that individually are below the threshold but sum to INR 10 lakh in a month.

**Reporting file:** CTR filed monthly by the 15th of the succeeding month.

## 2. Suspicious Transaction Reporting (STR)

STRs must be filed within **7 working days** of arriving at a conclusion that any transaction is suspicious. No monetary threshold applies.

## 3. Rapid Movement — Pass-Through Windows

The RBI Master Direction requires banks to establish **transaction-pattern parameters** including detection of accounts where funds are received and dispatched within a short window without an evident economic purpose.

**R181 nexus (India):** the pass-through-window parameter for R181 in India is configured at **72 hours** in the Rule Catalog (`country_overrides.IN.pass_through_window_hours`). This aligns with typical industry practice for RBI-supervised entities, calibrated to catch mule-account and funnel patterns while allowing legitimate corporate cash-management flows.

## 4. Cross-Border Transactions — FEMA Nexus

Cross-border transactions are additionally governed by **FEMA (Foreign Exchange Management Act) 1999**. All outward remittances above **USD 250,000 per financial year per resident individual** require Liberalised Remittance Scheme (LRS) tracking. Aggregation across banks is done centrally by AD Category-I banks.

**R174 nexus:** cross-border layering detection consults LRS aggregation for individual-segment customers in India.

## 5. Customer Segments & Risk Categorisation

RBI Master Direction §12 mandates customer risk categorisation into **Low / Medium / High**. Retail, MSME, and Corporate segments each have differentiated CDD depth. Politically Exposed Persons require senior management approval.

## 6. Record Retention

**Five years** from the date of transaction or termination of relationship, whichever is later, per PMLA §12(1)(a) and Rule 6.
