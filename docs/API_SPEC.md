# RailSync AI - REST API Specification

**Base URL**: `http://localhost:8000`  
**Swagger UI**: `http://localhost:8000/docs`  
**ReDoc**: `http://localhost:8000/redoc`  
**Safety Header**: `X-RailSync-Advisory: ADVISORY ONLY. HUMAN CONTROLLER APPROVAL REQUIRED. RAILSYNC AI DOES NOT CONTROL SIGNALING, INTERLOCKING OR KAVACH.`

---

## 1. Maintenance Requests (`/api/requests`)

### Create Request
- **Endpoint**: `POST /api/requests`
- **Description**: Submits a maintenance request via preset issue button, free-text description, or speech transcript.
- **Request Body**:
```json
{
  "section_id": "TVC-QLN",
  "input_mode": "preset",
  "preset_type": "track_defect_weld",
  "duration_minutes": 120,
  "metadata": {"reported_by": "P-Way SSE Kollam"}
}
```
- **Response** (`201 Created`):
```json
{
  "status": "success",
  "data": {
    "request_id": "MR-20260927-9F12A4",
    "section_id": "TVC-QLN",
    "raw_text": "Preset: Track Rail Weld Defect - Rail weld fracture / defect identified during USFD testing requiring immediate re-welding.",
    "status": "RECEIVED",
    "duration_minutes": 120,
    "created_at": "2026-09-27T08:50:00Z"
  }
}
```

### Trigger LAYA Triage
- **Endpoint**: `POST /api/requests/{id}/triage`
- **Description**: Invokes LAYA System 1 non-autoregressive decision engine to predict department, operational priority, and safety criticality with calibrated probability distributions.
- **Response** (`200 OK`):
```json
{
  "status": "success",
  "data": {
    "department": {
      "label": "P-Way",
      "probabilities": {
        "P-Way": 0.82,
        "S&T": 0.08,
        "TRD/OHE": 0.06,
        "Operating": 0.03,
        "Other": 0.01
      }
    },
    "priority": {
      "label": "HIGH",
      "probabilities": {
        "LOW": 0.04,
        "NORMAL": 0.18,
        "HIGH": 0.68,
        "CRITICAL": 0.10
      }
    },
    "safety_critical": {
      "label": true,
      "probability": 0.72
    },
    "latency_ms": 1.15,
    "model_version": "convaiinnovations/laya@0.3.20"
  }
}
```

### List Maintenance Requests
- **Endpoint**: `GET /api/requests?status={status}&section_id={section_id}`
- **Response** (`200 OK`):
```json
{
  "status": "success",
  "count": 1,
  "data": [
    {
      "id": "MR-20260927-9F12A4",
      "section_id": "TVC-QLN",
      "raw_text": "Track Rail Weld Defect",
      "status": "TRIAGED",
      "input_mode": "preset",
      "preset_type": "track_defect_weld",
      "duration_minutes": 120,
      "scheduled_start_min": null,
      "scheduled_end_min": null,
      "triage": {
        "department": "P-Way",
        "priority": "HIGH",
        "safety_critical": true,
        "confidence": 0.82,
        "latency_ms": 1.15,
        "model_version": "convaiinnovations/laya@0.3.20"
      }
    }
  ]
}
```

---

## 2. Block Planning Engine (`/api/planning`)

### Run Block Planning
- **Endpoint**: `POST /api/planning/run`
- **Description**: Runs deterministic heuristic search or Google OR-Tools CP-SAT constraint solver to discover conflict-free candidate maintenance windows against live train timetables.
- **Request Body**:
```json
{
  "request_id": "MR-20260927-9F12A4",
  "horizon_hours": 48,
  "max_candidates": 3,
  "auto_evaluate_with_laya": true
}
```
- **Response** (`200 OK`):
```json
{
  "status": "success",
  "data": {
    "request_id": "MR-20260927-9F12A4",
    "candidate_count": 3,
    "candidates": [
      {
        "candidate_id": "CW-CP-8a21bf-1",
        "section_id": "TVC-QLN",
        "start_time_min": 120,
        "end_time_min": 240,
        "duration_min": 120,
        "affected_trains": [],
        "conflicts": [],
        "feasibility_status": "FEASIBLE",
        "optimality_score": 96.5,
        "planner_latency_ms": 18.4,
        "laya_evaluation": {
          "risk_level": "LOW",
          "risk_probabilities": {"LOW": 0.90, "MEDIUM": 0.08, "HIGH": 0.02, "CRITICAL": 0.0},
          "conflicts_high_priority_service": false,
          "recommended_action": "APPROVE_REVIEW",
          "confidence": 0.95,
          "latency_ms": 1.05
        }
      }
    ]
  }
}
```

---

## 3. Candidate Risk Evaluation (`/api/candidates`)

### Evaluate Candidate Window with LAYA
- **Endpoint**: `POST /api/candidates/{candidate_id}/evaluate`
- **Description**: Second LAYA decision point evaluating candidate window operational disruption risk.
- **Response** (`200 OK`):
```json
{
  "status": "success",
  "data": {
    "candidate_id": "CW-CP-8a21bf-1",
    "risk_level": "LOW",
    "risk_probabilities": {"LOW": 0.90, "MEDIUM": 0.08, "HIGH": 0.02, "CRITICAL": 0.0},
    "conflicts_high_priority_service": false,
    "recommended_action": "APPROVE_REVIEW",
    "confidence": 0.95,
    "latency_ms": 1.05,
    "model_version": "convaiinnovations/laya@0.3.20"
  }
}
```

---

## 4. Human Section Controller Workflow

### Controller Approval
- **Endpoint**: `POST /api/requests/{id}/approve`
- **Request Body**:
```json
{
  "candidate_id": "CW-CP-8a21bf-1",
  "actor_name": "Sh. R. Sharma",
  "actor_role": "Section Controller",
  "reason": "Approved for 02:00-04:00 shadow night window."
}
```
- **Response** (`200 OK`):
```json
{
  "status": "success",
  "message": "Block authorized by Sh. R. Sharma",
  "data": {
    "request_id": "MR-20260927-9F12A4",
    "status": "APPROVED",
    "start": 120
  }
}
```

### Controller Rejection
- **Endpoint**: `POST /api/requests/{id}/reject`
- **Request Body**:
```json
{
  "candidate_id": "CW-CP-8a21bf-1",
  "actor_name": "Sh. R. Sharma",
  "actor_role": "Section Controller",
  "reason": "Clashes with unplanned Vande Bharat empty rake movement."
}
```

---

## 5. What-If Incident Engine (`/api/incidents`)

### Simulate Disruption
- **Endpoint**: `POST /api/incidents/simulate`
- **Request Body**:
```json
{
  "incident_type": "SIGNAL_MALFUNCTION",
  "section_id": "TVC-QLN",
  "description": "Signal aspect blanking at home signal",
  "expected_delay_min": 35
}
```
- **Response** (`200 OK`):
```json
{
  "status": "success",
  "data": {
    "incident_type": "SIGNAL_MALFUNCTION",
    "severity": "HIGH",
    "affects_active_block": true,
    "triggers_reoptimization": true,
    "affected_sections": ["TVC-QLN"],
    "confidence": 0.89,
    "latency_ms": 1.12,
    "model_version": "convaiinnovations/laya@0.3.20"
  }
}
```

---

## 6. Real-Time Stream & Telemetry

### Server-Sent Events (SSE)
- **Endpoint**: `GET /api/events`
- **Content-Type**: `text/event-stream`
- **Events**:
  - `request_created`
  - `laya_triage_completed`
  - `planner_completed`
  - `laya_candidate_evaluated`
  - `controller_approved`
  - `controller_rejected`
  - `incident_detected`
  - `reoptimization_triggered`

### Health & Metrics
- **Endpoint**: `GET /api/health`
- **Endpoint**: `GET /api/metrics` (includes measured LAYA average latency and planner latency)
- **Endpoint**: `GET /api/demo/data` (Southern Railway Kerala Section demo dataset)
