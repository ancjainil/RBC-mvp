# Synthetic Identity Fraud

## Overview
Synthetic identity fraud (SIF) involves the creation of a fictitious identity by combining real and fabricated information — most commonly a real Social Insurance Number (SIN) with a fabricated name, date of birth, and address. Unlike traditional identity theft, there is no direct victim whose identity has been stolen; instead, the fraudster constructs a new, plausible identity.

SIF is one of the fastest-growing and hardest-to-detect fraud types in Canada. Estimated losses to Canadian financial institutions exceed **$600M CAD annually**. The scheme typically plays out over months or years, making it difficult to detect until the "bust-out" event.

## The Lifecycle of a Synthetic Identity

### Phase 1: Identity Construction (Months 0–3)
- Fraudster obtains a real SIN, typically from a child, elderly person, or recent immigrant with no credit history
- Fabricates a name, address, and date of birth to attach to the SIN
- Applies for credit products that have minimal verification requirements

### Phase 2: Credit Building (Months 3–18)
- Applies for a secured credit card or retail store card
- Makes small, regular purchases and pays the balance on time
- Gradually applies for higher credit limit products
- The synthetic identity builds a legitimate-looking credit profile
- May be added as an authorized user on a real person's good-credit account ("piggybacking")

### Phase 3: Credit Maximization (Months 18–30)
- Applies for multiple credit products in a short window (credit washing)
- Takes cash advances across multiple accounts
- Opens new accounts and immediately maximizes limits

### Phase 4: Bust-Out
- All available credit lines are maxed out within a short period (days to weeks)
- All payments stop; accounts go delinquent simultaneously
- The synthetic identity effectively ceases to exist
- Estimated average bust-out value: **$80,000–$200,000 CAD per identity**

## Behavioral Indicators

### Application Signals
- SIN associated with a date of birth that would make the person a minor (SIN assigned at birth but no credit history until adulthood is normal; a 5-year-old applying for credit is not)
- Address is a mail forwarding service, PO box, or virtual office
- Phone number is a VoIP number with no carrier record
- Email domain created recently (< 90 days old)
- Multiple applications with the same address but different names within 30 days

### Transaction Signals
- Account opened with promotional balance transfer, immediately maxed
- Pattern of minimum payments for 12+ months followed by sudden cessation
- All transactions concentrated in a short window before default
- Cash advances immediately after credit limit increase
- Purchases at pawnshops, gold dealers, or gift card merchants (easily liquidated goods)

### Credit Bureau Signals
- "Thin file" — very few tradelines despite the account being open for 2+ years
- No utility accounts, no rental history, no mortgage
- All tradelines opened within a narrow window
- Multiple hard inquiries in a short period (credit washing signal)

## Detection Techniques

### Identity Graph Analysis
Build a graph connecting:
- SIN → all accounts ever associated with it
- Address → all applicants at that address
- Phone/email → all accounts using that contact method
- Device fingerprint → all accounts applied for from that device

Synthetic identities often share nodes in this graph with other synthetic identities created by the same fraud ring.

### Velocity Rules
- > 3 credit applications within 60 days = moderate flag
- Credit limit increase request within 90 days of account opening = flag
- Cash advance within 30 days of first purchase = flag
- Account utilization > 90% within first 6 months = flag

## Canadian Context
- Canadian SINs beginning with **9** are issued to temporary residents and are time-limited; a 9-series SIN used on a credit application requires verification of the associated work/study permit expiry
- The Canadian Credit Reporting Act limits the information available in credit reports compared to the US; fraudsters exploit this gap
- FINTRAC requires SIN verification for accounts exceeding $25,000 in deposits; synthetic identities often structure deposits below this threshold

## References
- Financial Consumer Agency of Canada: Identity Fraud Statistics 2023
- FINTRAC Guideline 6C: Record Keeping for Life Insurance Companies
- TransUnion Canada: Synthetic Identity Fraud Report 2022
