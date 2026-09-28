import json
from datetime import datetime
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from app.db.database import Base


class MaintenanceRequestORM(Base):
    __tablename__ = "maintenance_requests"

    id = Column(String(64), primary_key=True, index=True)
    section_id = Column(String(32), nullable=False, index=True)
    raw_text = Column(Text, nullable=False)
    language = Column(String(16), default="en")
    input_mode = Column(String(16), default="text")
    preset_type = Column(String(64), nullable=True)
    department = Column(String(32), nullable=True)
    priority = Column(String(32), nullable=True)
    asset_id = Column(String(64), nullable=True)
    duration_minutes = Column(Integer, default=120)
    status = Column(String(32), default="RECEIVED", index=True)
    scheduled_start_min = Column(Integer, nullable=True)
    scheduled_end_min = Column(Integer, nullable=True)
    selected_candidate_id = Column(String(64), nullable=True)
    metadata_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    decisions = relationship("LayaDecisionORM", back_populates="request", cascade="all, delete-orphan")
    planning_runs = relationship("PlanningRunORM", back_populates="request", cascade="all, delete-orphan")
    candidates = relationship("CandidateWindowORM", back_populates="request", cascade="all, delete-orphan")
    human_actions = relationship("HumanActionORM", back_populates="request", cascade="all, delete-orphan")


class LayaDecisionORM(Base):
    __tablename__ = "laya_decisions"

    id = Column(String(64), primary_key=True, index=True)
    request_id = Column(String(64), ForeignKey("maintenance_requests.id"), nullable=False, index=True)
    decision_point = Column(String(32), nullable=False) # TRIAGE, CANDIDATE_EVAL, INCIDENT
    department = Column(String(32), nullable=True)
    department_probs = Column(Text, nullable=True) # JSON
    priority = Column(String(32), nullable=True)
    priority_probs = Column(Text, nullable=True) # JSON
    safety_critical = Column(Boolean, nullable=True)
    safety_critical_prob = Column(Float, nullable=True)
    confidence = Column(Float, nullable=False)
    latency_ms = Column(Float, nullable=False)
    model_version = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    request = relationship("MaintenanceRequestORM", back_populates="decisions")


class PlanningRunORM(Base):
    __tablename__ = "planning_runs"

    id = Column(String(64), primary_key=True, index=True)
    request_id = Column(String(64), ForeignKey("maintenance_requests.id"), nullable=False, index=True)
    solver_type = Column(String(32), nullable=False) # ortools, deterministic
    status = Column(String(32), default="COMPLETED")
    latency_ms = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    request = relationship("MaintenanceRequestORM", back_populates="planning_runs")
    candidates = relationship("CandidateWindowORM", back_populates="planning_run", cascade="all, delete-orphan")


class CandidateWindowORM(Base):
    __tablename__ = "candidate_windows"

    id = Column(String(64), primary_key=True, index=True)
    planning_run_id = Column(String(64), ForeignKey("planning_runs.id"), nullable=False, index=True)
    request_id = Column(String(64), ForeignKey("maintenance_requests.id"), nullable=False, index=True)
    section_id = Column(String(32), nullable=False)
    start_time_min = Column(Integer, nullable=False)
    end_time_min = Column(Integer, nullable=False)
    duration_min = Column(Integer, nullable=False)
    affected_trains_json = Column(Text, default="[]")
    conflicts_json = Column(Text, default="[]")
    feasibility_status = Column(String(32), default="FEASIBLE")
    optimality_score = Column(Float, default=0.0)
    constraint_violations_json = Column(Text, default="[]")
    planner_latency_ms = Column(Float, default=0.0)
    laya_evaluation_json = Column(Text, nullable=True) # Cached LAYA candidate evaluation
    created_at = Column(DateTime, default=datetime.utcnow)

    planning_run = relationship("PlanningRunORM", back_populates="candidates")
    request = relationship("MaintenanceRequestORM", back_populates="candidates")


class IncidentORM(Base):
    __tablename__ = "incidents"

    id = Column(String(64), primary_key=True, index=True)
    incident_type = Column(String(64), nullable=False)
    section_id = Column(String(32), nullable=False, index=True)
    train_no = Column(String(32), nullable=True)
    delay_min = Column(Integer, default=0)
    description = Column(Text, nullable=False)
    severity = Column(String(32), default="NORMAL")
    affects_active_block = Column(Boolean, default=False)
    triggers_reoptimization = Column(Boolean, default=False)
    affected_sections_json = Column(Text, default="[]")
    laya_confidence = Column(Float, default=0.0)
    latency_ms = Column(Float, default=0.0)
    model_version = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class HumanActionORM(Base):
    __tablename__ = "human_actions"

    id = Column(String(64), primary_key=True, index=True)
    request_id = Column(String(64), ForeignKey("maintenance_requests.id"), nullable=False, index=True)
    candidate_id = Column(String(64), nullable=True)
    actor_name = Column(String(64), nullable=False)
    actor_role = Column(String(64), nullable=False)
    action = Column(String(32), nullable=False) # APPROVED, REJECTED, REOPTIMIZE_REQUESTED
    reason = Column(Text, nullable=True)
    checklist_json = Column(Text, default="{}")
    timestamp = Column(DateTime, default=datetime.utcnow)

    request = relationship("MaintenanceRequestORM", back_populates="human_actions")


class AuditEventORM(Base):
    __tablename__ = "audit_events"

    id = Column(String(64), primary_key=True, index=True)
    event_type = Column(String(64), nullable=False, index=True)
    request_id = Column(String(64), nullable=True, index=True)
    actor = Column(String(64), default="system")
    input_payload = Column(Text, default="{}")
    output_payload = Column(Text, default="{}")
    model_version = Column(String(64), nullable=True)
    latency_ms = Column(Float, nullable=True)
    decision = Column(String(64), nullable=True)
    metadata_json = Column(Text, default="{}")
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
