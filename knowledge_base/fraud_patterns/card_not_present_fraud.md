# Card-Not-Present (CNP) Fraud Patterns

## Overview
CNP fraud occurs when stolen card credentials are used for transactions where the physical card is not required (online, telephone, mail order). CNP fraud accounted for approximately **73% of total card fraud losses in Canada** in 2023 (Canadian Bankers Association Annual Report), with estimated losses exceeding $700M CAD.

The shift to chip-and-PIN (EMV) at physical terminals has driven fraudsters almost exclusively online, making CNP the dominant fraud vector for Canadian financial institutions.

## Common Indicators

### Transaction-Level Signals
- Transaction from a new device fingerprint or IP address not previously associated with the cardholder
- Shipping address differs from billing address (address verification system mismatch)
- Multiple rapid purchases from different online merchants within a short time window (< 2 hours)
- High-value electronics, gift cards, or easily resalable goods
- IP geolocation inconsistent with cardholder's known residence or travel history
- Use of VPN, TOR exit nodes, or datacenter IP ranges to mask true location
- Failed CVV/AVS verification followed by a successful attempt (credential stuffing pattern)
- Multiple browser sessions originating from the same IP against different accounts

### Velocity Patterns
- **Card-testing behaviour**: One or more low-value transactions ($0.50–$5.00) at digital merchants (Steam, iTunes, PayPal verification) followed by a high-value purchase within 1–4 hours. This pattern is used to verify card validity before committing a large fraudulent purchase.
- Multiple declined transactions from the same device or IP followed by a successful one
- Burst of 5+ online transactions within a 30-minute window for a customer with no prior online shopping history

### Merchant-Category Signals
- Gift card purchases exceeding $200 at a single merchant (potential money laundering)
- Electronics purchases at unfamiliar vendors when the customer has no prior electronics purchase history
- Transactions at merchants outside Canada for customers with no international travel history
- Digital goods/subscription purchases at unknown merchants

## Canadian-Specific Indicators
- Cross-border online transactions from US/international merchants when cardholder has no history of cross-border shopping
- Transactions at merchants not registered with Payments Canada or lacking proper MCC coding
- Gift card purchases exceeding $500 at multiple retailers within 48 hours (FINTRAC suspicious transaction indicator — potential structuring)
- Use of prepaid VISA/Mastercard cards at online gambling or cryptocurrency exchanges

## Detection Approach
1. **Device intelligence**: Cross-reference device fingerprint against known-good devices for the account
2. **Geolocation analysis**: Compare transaction IP geolocation against registered address and recent transaction locations
3. **Velocity scoring**: Calculate transactions per hour/day for the card and flag deviations from the customer's historical norm
4. **Merchant reputation**: Cross-reference against known high-risk merchant lists
5. **Behavioural biometrics**: Time-on-page, mouse movement patterns, typing cadence (for mobile banking)

## Recommended Actions
| Risk Level | Recommended Action |
|---|---|
| Low (single new merchant, small amount) | Approve with monitoring |
| Medium (new device + unfamiliar merchant) | Step-up authentication (OTP) |
| High (new device + high amount + unusual category) | Decline and notify customer |
| Critical (impossible geo + new device + high amount) | Block and escalate to fraud team |

## References
- Canadian Bankers Association: Payment Card Fraud Statistics 2023
- Payments Canada: Real-time Rail Fraud Framework v2.1
- FINTRAC: Indicators of Money Laundering in Financial Transactions, Guideline 2
