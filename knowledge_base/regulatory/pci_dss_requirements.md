# PCI DSS v4.0 Requirements Summary — Fraud Detection Relevance

## Overview
The Payment Card Industry Data Security Standard (PCI DSS) version 4.0 (released March 2022, mandatory compliance by March 2025) establishes baseline security requirements for any organisation that stores, processes, or transmits cardholder data.

This document summarises PCI DSS requirements most relevant to AI-based fraud detection systems.

---

## Requirement 10: Log and Monitor All Access to System Components and Cardholder Data

### 10.2 — Audit Logs
- All fraud scoring system logs must capture: user/system ID, event type, date/time, success/failure, origination of event, identity of affected data
- Logs must be retained for **at least 12 months**, with the most recent 3 months available for immediate analysis
- Fraud detection AI systems accessing cardholder data must maintain audit trails of every query

### 10.4 — Time Synchronization
- All system clocks must be synchronized (NTP); accurate timestamps are critical for geo-velocity analysis

### 10.7 — Failure of Security Controls
- Automated alerts when fraud detection systems fail or produce anomalous outputs (e.g., all transactions scored as LOW risk for an extended period)

---

## Requirement 11: Test Security of Systems and Networks Regularly

### 11.6 — Change- and Tamper-Detection for Payment Pages
- For online payment flows, detect unauthorized modification of payment page scripts
- Relevant to CNP fraud prevention — a compromised payment page can exfiltrate card data

---

## Requirement 12: Support Information Security with Organisational Policies and Programs

### 12.3 — Hardware and Software Technologies
- AI/ML models used for fraud detection must be inventoried and reviewed at least annually
- Model documentation must include training data provenance, version history, and explainability notes

### 12.10 — Incident Response Plan
- Must include a fraud event response playbook
- Fraud detection AI system must be integrated into the incident response workflow — if the model raises a CRITICAL alert, escalation path must be defined

---

## Cardholder Data Handling in Fraud Detection Systems

### What Data Can Be Used
| Data Element | Storage | Processing | Transmission |
|---|---|---|---|
| Primary Account Number (PAN) | Must be masked/tokenized | Permitted | Must be encrypted |
| Cardholder name | Permitted | Permitted | Permitted |
| Service code | Permitted | Permitted | Permitted |
| Expiration date | Permitted | Permitted | Permitted |
| CVV/CVC | **NEVER store** | During authorization only | Encrypted only |
| PIN/PIN block | **NEVER store** | HSM only | **NEVER** in plaintext |

**Critical for AI fraud detection**: The model must never be trained on or log raw PANs. Use tokenized card identifiers (tokens) or masked representations (first 6 + last 4 digits) only.

### Tokenization
PCI DSS v4.0 strongly recommends tokenization as the primary method of reducing PCI DSS scope:
- Replace the PAN with a token in all fraud detection model inputs
- Maintain a secure token vault that maps tokens back to PANs only for authorized settlement processes
- The fraud detection AI system operates on tokens, not real PANs — dramatically reducing the blast radius of a model breach

---

## AI/ML Model Compliance Considerations

### Explainability (Requirement 12.3.2)
PCI DSS v4.0 introduces a "targeted risk analysis" requirement. For AI fraud detection:
- Every fraud decision must have an **explainable audit trail**
- Black-box models must be supplemented with explanation outputs (SHAP values, LIME, or structured reasoning from LLM agents)
- The explanation must be retrievable on demand for chargebacks and regulatory inquiries

### Model Drift Monitoring
- Fraud detection models must be monitored for performance degradation
- Statistical process control charts or equivalent monitoring for precision/recall drift
- Alert when false positive rate increases by > 20% from baseline for 5+ consecutive days

### Data Retention for Model Artifacts
- Training datasets: 12-month minimum retention with access logging
- Model weights/checkpoints: 24-month minimum retention
- Inference logs (input features + output scores): 12-month minimum with masked PAN data

---

## Relevant Standards and References
- PCI Security Standards Council: PCI DSS v4.0 (March 2022)
- PCI SSC Information Supplement: Protecting Telephone-based Payment Card Data
- OSFI Guideline B-10: Third-Party Risk Management (for AI vendors processing cardholder data)
- ISO/IEC 27001:2022 — Information Security Management Systems
