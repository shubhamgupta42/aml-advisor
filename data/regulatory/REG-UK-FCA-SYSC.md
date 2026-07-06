# REG-UK-FCA-SYSC · UK Financial Conduct Authority — Systems & Controls (Financial Crime)

**Document ID:** REG-UK-FCA-SYSC-v1
**Jurisdiction:** UK
**Regulator:** FCA (Financial Conduct Authority)
**Primary Source:** SYSC 6.3 (Financial Crime); FCG (Financial Crime Guide) Part 1, Ch. 3
**Related Legislation:** Money Laundering Regulations 2017 (as amended 2019, 2022); POCA 2002
**Source Type:** external_regulatory
**Rule Nexus:** R168, R174, R181

---

## 1. Transaction Monitoring Obligation

Under **SYSC 6.3.1G** and **MLR 2017 Regulation 19**, a firm must establish and maintain policies, controls and procedures to mitigate and manage effectively the risks of money laundering. This includes **ongoing monitoring** of business relationships — i.e. scrutiny of transactions to ensure they are consistent with the firm's knowledge of the customer, and keeping documents and information up to date.

**Implication for our system:** the MDD → Rule Catalog → RTCA chain is the auditable artefact that evidences the firm's transaction monitoring methodology to the FCA.

## 2. Risk-Based Approach

MLR 2017 mandates a **risk-based approach (RBA)**. Firms must assess ML/TF risk at customer, product, geography, and channel level, and calibrate controls accordingly. The RTCA (Rule-to-Coverage-Assessment) directly implements this — coverage decisions are documented per (country × typology × segment).

## 3. Suspicious Activity Reporting

Where a firm has knowledge or suspicion of money laundering, a **SAR must be filed with the NCA (National Crime Agency)** without delay. There is no monetary threshold — the trigger is suspicion, not amount.

**Contrast with US CTR:** the UK regime is suspicion-based, not threshold-based. This is why R168-style structuring detection is calibrated differently in UK deployments — see RTCA for UK-specific tuning.

## 4. Record Retention

Records supporting CDD, transaction monitoring alerts, and SAR filings must be retained for **five years** after the end of the business relationship or transaction.

## 5. Governance & MLRO

The firm must appoint a **Money Laundering Reporting Officer (MLRO)** with sufficient seniority and independence. The MLRO is the accountable individual for both internal alert triage and external SAR filing decisions.
