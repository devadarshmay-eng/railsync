"""Controlled Indian Railways Demo Dataset (Kerala Section, Southern Railway).

CLEARLY MARKED AS:
DEMO / SIMULATED OPERATIONAL DATA
NOT LIVE OPERATIONAL FEEDS.
"""

from typing import Dict, List
from app.domain.models import SectionModel, StationModel, TrainModel, TrainScheduleEntry, SectionOccupancy

DATA_DISCLAIMER = "DEMO / SIMULATED OPERATIONAL DATA - SOUTHERN RAILWAY KERALA SECTION"

STATIONS: Dict[str, StationModel] = {
    "TVC": StationModel(code="TVC", name="Thiruvananthapuram Central", lat=8.48, lon=76.95, master="Sh. Rajesh Kumar"),
    "QLN": StationModel(code="QLN", name="Kollam Junction", lat=8.88, lon=76.59, master="Sh. Anil Thomas"),
    "KYJ": StationModel(code="KYJ", name="Kayamkulam Junction", lat=9.17, lon=76.50, master="Smt. Latha Nair"),
    "ALLP": StationModel(code="ALLP", name="Alappuzha", lat=9.49, lon=76.33, master="Sh. Suresh Pillai"),
    "KTYM": StationModel(code="KTYM", name="Kottayam", lat=9.59, lon=76.52, master="Sh. Jose Mathew"),
    "ERS": StationModel(code="ERS", name="Ernakulam Junction", lat=9.97, lon=76.28, master="Sh. Vinod Menon"),
    "TCR": StationModel(code="TCR", name="Thrissur", lat=10.52, lon=76.21, master="Smt. Geetha S."),
    "SRR": StationModel(code="SRR", name="Shoranur Junction", lat=10.76, lon=76.27, master="Sh. Balan K."),
    "TIR": StationModel(code="TIR", name="Tirur", lat=10.91, lon=75.92, master="Sh. Faizal M."),
    "CLT": StationModel(code="CLT", name="Kozhikode", lat=11.25, lon=75.78, master="Sh. Suresh Babu"),
    "CAN": StationModel(code="CAN", name="Kannur", lat=11.87, lon=75.37, master="Sh. Nandakumar"),
    "KGQ": StationModel(code="KGQ", name="Kasaragod", lat=12.49, lon=74.99, master="Sh. Ramachandran"),
}

SECTIONS: Dict[str, SectionModel] = {
    "TVC-QLN": SectionModel(id="TVC-QLN", from_station="TVC", to_station="QLN", km=65, lines=2),
    "QLN-KYJ": SectionModel(id="QLN-KYJ", from_station="QLN", to_station="KYJ", km=35, lines=2),
    "KYJ-ALLP": SectionModel(id="KYJ-ALLP", from_station="KYJ", to_station="ALLP", km=38, lines=2),
    "ALLP-ERS": SectionModel(id="ALLP-ERS", from_station="ALLP", to_station="ERS", km=58, lines=2),
    "QLN-KTYM": SectionModel(id="QLN-KTYM", from_station="QLN", to_station="KTYM", km=80, lines=1), # Single line bottle-neck
    "KTYM-ERS": SectionModel(id="KTYM-ERS", from_station="KTYM", to_station="ERS", km=65, lines=2),
    "ERS-TCR": SectionModel(id="ERS-TCR", from_station="ERS", to_station="TCR", km=74, lines=2),
    "TCR-SRR": SectionModel(id="TCR-SRR", from_station="TCR", to_station="SRR", km=30, lines=3), # Triple line trunk
    "SRR-TIR": SectionModel(id="SRR-TIR", from_station="SRR", to_station="TIR", km=45, lines=2),
    "TIR-CLT": SectionModel(id="TIR-CLT", from_station="TIR", to_station="CLT", km=42, lines=2),
    "CLT-CAN": SectionModel(id="CLT-CAN", from_station="CLT", to_station="CAN", km=89, lines=2),
    "CAN-KGQ": SectionModel(id="CAN-KGQ", from_station="CAN", to_station="KGQ", km=85, lines=1), # Single line bottle-neck
}

MAINTENANCE_PRESETS = {
    "track_defect_weld": {
        "id": "track_defect_weld",
        "name": "Track Rail Weld Defect",
        "department": "P-Way",
        "default_duration_min": 120,
        "blocks_section": True,
        "asset_type": "track",
        "description": "Rail weld fracture / defect identified during USFD testing requiring immediate re-welding."
    },
    "deep_screening_ballast": {
        "id": "deep_screening_ballast",
        "name": "Deep Screening & Ballast Packing",
        "department": "P-Way",
        "default_duration_min": 180,
        "blocks_section": True,
        "asset_type": "track",
        "description": "Mechanized ballast cleaning and tamping machine block."
    },
    "bridge_bearing_greasing": {
        "id": "bridge_bearing_greasing",
        "name": "Bridge Bearing Inspection & Greasing",
        "department": "P-Way",
        "default_duration_min": 150,
        "blocks_section": True,
        "asset_type": "bridge",
        "description": "Major girder bridge inspection and bearing servicing."
    },
    "ohe_catenary_replacement": {
        "id": "ohe_catenary_replacement",
        "name": "OHE Contact Wire Replacement",
        "department": "TRD/OHE",
        "default_duration_min": 90,
        "blocks_section": True,
        "asset_type": "ohe",
        "description": "Power block for contact wire wear replacement and stagger correction."
    },
    "substation_transformer_oil": {
        "id": "substation_transformer_oil",
        "name": "Traction Substation Transformer Servicing",
        "department": "TRD/OHE",
        "default_duration_min": 60,
        "blocks_section": False,
        "asset_type": "substation",
        "description": "Traction substation transformer testing; does not disrupt section running."
    },
    "signal_point_machine": {
        "id": "signal_point_machine",
        "name": "Point Machine Setting & Lubrication",
        "department": "S&T",
        "default_duration_min": 45,
        "blocks_section": True,
        "asset_type": "point",
        "description": "Turnout point motor adjustment and detection circuit testing."
    },
    "track_circuit_failure": {
        "id": "track_circuit_failure",
        "name": "Track Circuit Drop Investigation",
        "department": "S&T",
        "default_duration_min": 60,
        "blocks_section": False,
        "asset_type": "signal",
        "description": "Intermittent track circuit drop and relay box servicing."
    }
}

TRAIN_DEFINITIONS = [
    {"no": "12076", "name": "Jan Shatabdi Express", "type": "JSH", "route": ["TVC", "QLN", "KYJ", "ALLP", "ERS"], "dep": 6 * 60, "speed": 65},
    {"no": "16302", "name": "Venad Express", "type": "EXP", "route": ["TVC", "QLN", "KYJ", "ALLP", "ERS", "TCR", "SRR"], "dep": 5 * 60 + 30, "speed": 60},
    {"no": "16650", "name": "Parasuram Express", "type": "EXP", "route": ["TVC", "QLN", "KYJ", "ALLP", "ERS", "TCR", "SRR", "TIR", "CLT", "CAN"], "dep": 4 * 60 + 55, "speed": 60},
    {"no": "12617", "name": "Mangala Lakshadweep Exp", "type": "SUP", "route": ["ERS", "TCR", "SRR", "TIR", "CLT", "CAN", "KGQ"], "dep": 7 * 60, "speed": 65},
    {"no": "16304", "name": "Vanchinad Express", "type": "EXP", "route": ["TVC", "QLN", "KTYM", "ERS"], "dep": 5 * 60 + 45, "speed": 55},
    {"no": "16305", "name": "Intercity Express", "type": "EXP", "route": ["ERS", "TCR", "SRR", "TIR", "CLT", "CAN"], "dep": 6 * 60 + 15, "speed": 60},
    {"no": "16604", "name": "Maveli Express", "type": "EXP", "route": ["TVC", "QLN", "KYJ", "ALLP", "ERS", "TCR", "SRR", "TIR", "CLT", "CAN"], "dep": 18 * 60, "speed": 60},
    {"no": "16347", "name": "Mangalore Express", "type": "EXP", "route": ["TVC", "QLN", "KYJ", "ALLP", "ERS", "TCR", "SRR", "TIR", "CLT", "CAN", "KGQ"], "dep": 20 * 60 + 30, "speed": 60},
    {"no": "06425", "name": "MEMU TVC–QLN", "type": "MEM", "route": ["TVC", "QLN"], "dep": 7 * 60 + 30, "speed": 45},
    {"no": "06426", "name": "MEMU QLN–TVC", "type": "MEM", "route": ["QLN", "TVC"], "dep": 9 * 60 + 15, "speed": 45},
    {"no": "66611", "name": "MEMU ERS–TCR", "type": "MEM", "route": ["ERS", "TCR"], "dep": 8 * 60, "speed": 45},
    {"no": "66612", "name": "MEMU TCR–ERS", "type": "MEM", "route": ["TCR", "ERS"], "dep": 17 * 60 + 45, "speed": 45},
    {"no": "FRT01", "name": "Coal Freight (BOXN)", "type": "FRT", "route": ["ERS", "TCR", "SRR", "TIR", "CLT"], "dep": 2 * 60, "speed": 40},
    {"no": "FRT02", "name": "Container Freight", "type": "FRT", "route": ["CLT", "TIR", "SRR", "TIR", "ERS"], "dep": 14 * 60 + 30, "speed": 40},
]


def build_train_timetable() -> List[TrainModel]:
    """Generates precise station arrival/departure and section occupancies for all trains."""
    trains: List[TrainModel] = []
    
    for defn in TRAIN_DEFINITIONS:
        route = defn["route"]
        speed = defn["speed"]
        dep = defn["dep"]
        
        schedule = [TrainScheduleEntry(station=route[0], time_min=dep)]
        occupancies = []
        current_time = dep
        
        for i in range(len(route) - 1):
            st_a = route[i]
            st_b = route[i + 1]
            sec_id = f"{st_a}-{st_b}"
            sec = SECTIONS.get(sec_id)
            if not sec:
                sec_id = f"{st_b}-{st_a}"
                sec = SECTIONS.get(sec_id)
            
            km = sec.km if sec else 50
            transit_time = max(8, round(km / speed * 60))
            t0 = current_time
            t1 = current_time + transit_time
            
            occupancies.append(SectionOccupancy(section_id=sec.id if sec else sec_id, t0_min=t0, t1_min=t1))
            current_time = t1
            schedule.append(TrainScheduleEntry(station=st_b, time_min=current_time))
            current_time += 3 # 3-minute dwell time at station
            
        trains.append(TrainModel(
            no=defn["no"],
            name=defn["name"],
            type=defn["type"],
            route=route,
            dep_min=dep,
            speed_kmh=speed,
            schedule=schedule,
            occupancies=occupancies,
            delay_min=0
        ))
        
    return trains


# Pre-built timetable instance
TRAIN_TIMETABLE = build_train_timetable()
