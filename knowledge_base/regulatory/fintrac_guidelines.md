# FINTRAC AML/ATF Reporting Guidelines for Canadian Financial Institutions

## Overview
FINTRAC (Financial Transactions and Reports Analysis Centre of Canada) is Canada's financial intelligence unit, established under the *Proceeds of Crime (Money Laundering) and Terrorist Financing Act* (PCMLTFA). All federally regulated financial institutions, including banks, credit unions, and payment service providers, are required to report certain transactions to FINTRAC.

This document summarises the reporting thresholds and suspicious activity indicators most relevant to payment card fraud and automated fraud detection systems.

---

## Mandatory Reporting Requirements

### 1. Large Cash Transaction Reports (LCTR)
**Threshold: $10,000 CAD or more in cash in a single transaction or multiple transactions within 24 hours**

- Report must be filed within **15 calendar days** of the transaction
- Applies to cash received and cash sent
- Structuring (breaking up transactions to stay below $10,000) is a criminal offence under Section 7.1 of PCMLTFA
- **Structuring indicator**: Customer makes multiple cash transactions of $9,000, $9,500, or $9,800 within a 24-hour period = suspected structuring

### 2. Electronic Funds Transfer Reports (EFTR)
**Threshold: $10,000 CAD or more sent internationally in a single EFT or multiple EFTs within 24 hours**

- Covers wire transfers, SWIFT messages, and cryptocurrency-to-fiat conversions
- Report must be filed within **5 business days**
- Applies to both sending and receiving institutions

### 3. Suspicious Transaction Reports (STR)
**No dollar threshold — based on reasonable grounds to suspect the transaction is related to money laundering or terrorist financing**

- Must be filed within **30 calendar days** of forming the suspicion
- The "tipping off" prohibition: the subject must NOT be informed that a report has been filed
- STRs cover any amount — even a $5 transaction can trigger an STR if the context is suspicious

### 4. Terrorist Property Reports (TPR)
- Immediate reporting required if property is owned or controlled by a listed terrorist entity
- No financial threshold

---

## Suspicious Transaction Indicators Relevant to Card Fraud

### Gift Card Purchasing
- **Flag**: Gift card purchases exceeding **$500 in a single transaction** or **$2,000 in cumulative purchases within 30 days** from a single account
- **High suspicion**: Multiple gift card purchases at different retailers within 48 hours totaling > $1,000 (potential money laundering via gift card re-sale)
- Gift cards are a common vehicle for converting fraudulent card proceeds into untraceable value

### Cryptocurrency Transactions
- Rapid conversion of funds to cryptocurrency (especially non-KYC exchanges) following a suspicious inflow
- Multiple cryptocurrency exchange transactions below $10,000 within a short window (structuring)
- Use of peer-to-peer cryptocurrency platforms immediately after receiving funds

### Wire Transfers
- First-ever international wire transfer from an account, especially to high-risk jurisdictions (Nigeria, Romania, Latvia, Russia, Ukraine, Brazil — FATF high-risk list)
- Wire transfer amount just below $10,000 (potential structuring)
- Wire to a new beneficiary, especially when combined with a recent password/contact change

### Rapid Funds Movement
- Funds deposited and withdrawn (or transferred) within 24–72 hours ("pass-through" pattern)
- Multiple e-Transfers sent to different recipients in a short window
- Account balance brought to near-zero immediately following a credit limit increase

### Merchant-Related Indicators
- Cash refunds issued to a card where the cardholder has no record of a purchase at that merchant
- Merchant processing a disproportionate volume of international card transactions for a local retail business
- Transactions at money service businesses (MSBs) or currency exchanges by cardholders with no prior MSB history

---

## High-Risk Jurisdictions (FATF Guidance, 2024)
Transactions involving the following jurisdictions require enhanced due diligence:
- Iran, North Korea, Myanmar, Russia (enhanced monitoring since 2022)
- High-risk and monitored jurisdictions: Bulgaria, Burkina Faso, Cameroon, Croatia, Democratic Republic of Congo, Haiti, Jamaica, Mali, Mozambique, Nigeria, Panama, Philippines, Senegal, South Africa, South Sudan, Syria, Tanzania, Turkey, Uganda, United Arab Emirates, Vietnam, Yemen

---

## Record-Keeping Requirements
- All STRs, LCTRs, and EFTRs must be retained for a minimum of **5 years** from the date of the transaction
- Customer identification records must be retained for 5 years from the end of the business relationship
- Transaction records must be retained in a format retrievable within 30 days of a FINTRAC request

---

## Penalties for Non-Compliance
- Failure to report a LCTR: Up to **$500,000 CAD** per violation (administrative monetary penalty)
- Failure to report an STR: Up to **$100,000 CAD** per violation
- Intentional structuring: Criminal offence, up to **5 years imprisonment**

---

## Integration with Automated Fraud Detection
Automated fraud detection systems should:
1. **Flag transactions for STR review** when fraud probability > 0.80 AND any of the above indicators are present
2. **Auto-generate LCTR** for any cash transaction ≥ $10,000 (these are mandatory regardless of fraud risk)
3. **Hold outbound international wires** exceeding $10,000 for manual compliance review when the account has recent suspicious activity
4. **Block gift card transactions** exceeding $500 with a pending fraud alert on the account

---

## References
- *Proceeds of Crime (Money Laundering) and Terrorist Financing Act* (R.S.C. 2000, c. 17)
- FINTRAC Policy Interpretations: Suspicious Transaction Reporting
- FINTRAC Guideline 2: Suspicious Transactions
- FINTRAC Guideline 5: Suspicious Transaction Reporting for Securities Dealers
- Office of the Superintendent of Financial Institutions (OSFI): Guideline E-13, Regulatory Compliance Management
