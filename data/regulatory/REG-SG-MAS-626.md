# REG-SG-MAS-626 · Singapore MAS Notice 626 — AML/CFT for Banks

**Document ID:** REG-SG-MAS-626-v1
**Jurisdiction:** SG
**Regulator:** MAS (Monetary Authority of Singapore)
**Primary Source:** MAS Notice 626 (last major revision 2015, amendments through 2023)
**Related Legislation:** CDSA (Corruption, Drug Trafficking and Other Serious Crimes Act); TSOFA
**Source Type:** external_regulatory
**Rule Nexus:** R174, R181

---

## 1. Scope

MAS Notice 626 sets AML/CFT obligations for banks licensed under the **Banking Act** in Singapore. Digital-payment-token services and payment institutions are governed by parallel notices (PSN01, PSN02) — not covered here.

## 2. Ongoing Monitoring — §8

Banks must conduct **ongoing monitoring** of business relations, including:
- Scrutiny of transactions to ensure consistency with the customer's profile.
- Enhanced monitoring where risk is higher.
- Periodic review of CDD data.

**Implication for our system:** the RTCA's segment-level coverage decisions in Singapore must be justified against §8 — coverage gaps are audit findings.

## 3. Cash Transactions

Singapore has **no automatic CTR threshold** equivalent to the US BSA. Suspicion-based reporting is the primary regime (see §9). However, banks are expected to apply enhanced scrutiny to:
- Cash transactions **≥ SGD 20,000** as a common industry-baseline internal threshold.
- Structuring patterns designed to avoid internal or external reporting.

**R168 nexus:** the structuring rule in a Singapore deployment is calibrated against SGD, with the RTCA controlling in-scope segments.

## 4. Suspicious Transaction Reporting (STR)

Under **§9** and **§39 CDSA**, a bank must file an STR with the **Suspicious Transaction Reporting Office (STRO)** as soon as reasonably practicable upon forming a suspicion. There is no monetary threshold.

## 5. Cross-Border & Correspondent Banking

**§10** imposes enhanced measures on correspondent-banking relationships and cross-border wire transfers. Full originator/beneficiary information must accompany wire transfers **≥ SGD 1,500**.

**R174 nexus:** cross-border layering detection must consult the wire-info completeness signal — this is captured as a RTCA-tracked segment attribute for Singapore.

## 6. Record Retention

**Five years** after termination of business relations or completion of a transaction, per §14.
