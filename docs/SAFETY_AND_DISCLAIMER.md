# RailSync AI - Safety Mandate & Advisory Operational Framework

## 1. Statutory Notice & System Role
> **ADVISORY ONLY. HUMAN CONTROLLER APPROVAL REQUIRED.**  
> **RAILSYNC AI DOES NOT CONTROL SIGNALING, INTERLOCKING OR KAVACH.**

RailSync AI is engineered strictly as an **AI-Assisted Decision Support System** under Indian Railways General and Subsidiary Rules (G&SR). 

Under no circumstance does RailSync AI:
- Connect directly to Solid State Interlocking (SSI) / Route Relay Interlocking (RRI)
- Override Block Proving Axle Counters (BPAC)
- Modify Signal Aspect sequences
- Transmit direct commands to Kavach (Automatic Train Protection - ATP) on-board units or trackside transponders

## 2. Human Section Controller Authority
The authority to grant, regulate, suspend, cancel, or extend a Line Block or Power Block resides exclusively with the designated Section Controller on duty in the Divisional Control Office.

- RailSync AI calculates mathematically feasible candidate windows based on static timetables and reported headway constraints.
- LAYA evaluates operational network risk and outputs calibrated probability distributions.
- **Action Required**: The Section Controller must explicitly verify physical clearances, station master concurrence, and Kavach territory rules before executing the `POST /api/requests/{id}/approve` endpoint.

## 3. Auditability
Every recommendation, probability calculation, candidate window generation, and controller authorization is timestamped to microsecond precision and immutably recorded in the system audit log.
