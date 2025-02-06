# Merchant Collusion Fraud

## Overview
Merchant collusion fraud (also called merchant fraud or acquirer fraud) occurs when a merchant — or an employee of a merchant — participates in or facilitates fraudulent payment activity. The merchant may act independently or in coordination with external fraudsters.

Merchant collusion represents approximately **12% of total card fraud losses** in Canada and is particularly difficult to detect because the transactions appear legitimate from the card network's perspective.

## Types of Merchant Collusion

### 1. Refund Fraud / Credit Washing
The merchant processes fraudulent refunds to cards that never made a purchase at the store, effectively funneling money from the merchant account to a criminal's card.

**Indicators:**
- Refunds issued to cards with no corresponding purchase at that merchant
- Refunds issued outside of business hours or on holidays
- High refund-to-sales ratio (> 15% is a strong flag)
- Refunds for round-dollar amounts that don't match any real transaction
- Multiple refunds to different cards within a short window

### 2. Card Skimming (Merchant-Enabled)
A corrupt merchant employee attaches a skimming device to the POS terminal or retains card numbers from swipe transactions, then sells the card data or uses it for CNP fraud.

**Indicators:**
- Cluster of CNP fraud reports from cardholders who all transacted at the same merchant within a 2-week window
- Fraudulent CNP transactions appearing 7–30 days after a cluster of legitimate POS transactions at a specific merchant
- Common "compromise point" identified across multiple fraud reports

### 3. Bust-Out Merchant / Factoring
A fraudster establishes a legitimate-seeming merchant account, processes real cards through it (with or without cardholder consent), takes the settlement funds, and disappears.

**Indicators:**
- Merchant registered very recently (< 90 days) processing high volumes
- No website, social media presence, or verifiable business address
- Transactions clustered in a single day or week with no ongoing business activity
- Settlement funds immediately transferred out of the merchant bank account

### 4. Transaction Laundering (Undisclosed Aggregation)
A legitimate merchant processes transactions on behalf of an unlicensed business (e.g., an unlicensed online pharmacy, gambling site, or adult content site). The transactions appear to be for the legitimate merchant but are actually for the undisclosed business.

**Indicators:**
- Transaction volume far exceeds expected volume for the merchant's industry and size
- Chargeback rate significantly higher than industry average for the MCC
- Cardholders reporting they don't recognize the merchant name on their statement
- Merchant processing cards from geographies unrelated to their business location

### 5. Triangulation Fraud
The fraudster operates a fake online storefront offering goods at significantly below-market prices. They collect real payment card details from buyers, use stolen cards to purchase the goods from legitimate retailers and have them shipped to the buyers, and keep the real card funds.

**Indicators:**
- Merchant with a storefront identical to or closely mimicking a known legitimate retailer
- High volume of purchases at legitimate electronics/retail merchants shipped to addresses not associated with the cardholder

## Detection Techniques

### Merchant-Level Monitoring
- Track chargeback-to-transaction ratios by merchant (> 1% = warning; > 3% = critical)
- Monitor refund-to-sales ratios
- Velocity monitoring: transactions per hour for a given MID (Merchant ID)
- Geographic distribution of cardholders for a single merchant (normally concentrated near merchant location)

### Network Analysis
- Identify merchants that appear as the "last legitimate transaction" before a cluster of fraud events
- Compromise point analysis: if 30+ fraud reports share a common merchant in their recent transaction history, flag that merchant for investigation

### Behavioral Rules
- Flag merchants with first-week processing volume > 3× the average for their MCC and region
- Flag merchants with settlement accounts that were opened at the same time as the merchant account (typical for bust-out schemes)

## Canadian Regulatory Context
- Acquirers in Canada are required under Payments Canada rules to monitor merchants for excessive chargeback rates
- FINTRAC Guideline 4: Businesses Subject to FINTRAC — payment service providers processing > $1M/year must implement AML programs
- Merchants suspected of transaction laundering may be reported to the Canadian Anti-Fraud Centre (CAFC)

## References
- Payments Canada: Merchant Fraud Best Practices 2023
- FINTRAC Guideline 4: Implementation of a Compliance Regime
- Canadian Bankers Association: Merchant Fraud Advisory 2022
