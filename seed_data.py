"""
seed_data.py - Deterministic sample data generator for CivicEye Tumakuru.
Seeds 40 realistic civic complaints (15 road, 13 pollution, 12 water) across
Tumakuru city with authentic coordinates, AI triage fields, status progression,
and duplicate clusters.
"""

import os
import json
from datetime import datetime, timezone, timedelta

def get_seed_photos(category_folder):
    """
    Safely retrieves list of seed photos from static/seed/<category_folder>/
    Skips gracefully if folder does not exist or has no images.
    """
    valid_exts = {".jpg", ".jpeg", ".png", ".webp"}
    base_dir = os.path.dirname(os.path.abspath(__file__))
    folder_path = os.path.join(base_dir, "static", "seed", category_folder)
    if not os.path.exists(folder_path):
        return []
    
    files = []
    for f in sorted(os.listdir(folder_path)):
        if os.path.splitext(f.lower())[1] in valid_exts:
            files.append(f"static/seed/{category_folder}/{f}")
    return files


# 40 realistic seed complaints for Tumakuru
# Distribution: 15 road, 13 pollution, 12 water = 40 total
# Statuses: exactly 16 Resolved (40%), 8 In Progress, 6 Assigned, 5 Under Review, 5 Submitted
SEED_ITEMS = [
    # -------------------------------------------------------------------------
    # ROAD COMPLAINTS (15 items)
    # -------------------------------------------------------------------------
    {
        "tracking_id": "CE-2026-0001",
        "category": "road",
        "issue_type": "Pothole",
        "description": "Deep water-filled pothole near SIT main gate. Hazardous for student scooters.",
        "address_text": "B.H. Road, SIT Extension, Tumakuru",
        "lat": 13.3282, "lng": 77.1258,
        "severity": 4,
        "reasons": ["15cm deep pothole in primary carriage lane", "High collision risk for two-wheelers"],
        "detected_issue": "Deep Pothole Hazard",
        "summary": "Large water-filled road depression on B.H. Road near SIT college. Poses acute accident hazard for students and auto-rickshaws.",
        "suggested_action": "Fill crater with cold asphalt premix and compact flush with road grade.",
        "status": "Resolved",
        "days_ago": 26, "res_hours": 18,
        "dept_name": "Tumakuru City Corporation - Engineering Wing",
        "report_count": 1,
    },
    {
        "tracking_id": "CE-2026-0002",
        "category": "road",
        "issue_type": "Broken Curb",
        "description": "Concrete curb stones dislodged into vehicle lane opposite Town Hall shopping arcade.",
        "address_text": "MG Road, Opposite Town Hall, Tumakuru",
        "lat": 13.3395, "lng": 77.1020,
        "severity": 3,
        "reasons": ["Dislodged curb blocks roadway edge", "Pedestrian tripping hazard near shops"],
        "detected_issue": "Dislodged Curb Stones",
        "summary": "Concrete edge stones pushed into active carriageway along MG Road, obstructing traffic flow and pedestrian access.",
        "suggested_action": "Realign and cement curb stones with mortar bed.",
        "status": "Resolved",
        "days_ago": 22, "res_hours": 36,
        "dept_name": "Tumakuru City Corporation - Engineering Wing",
        "report_count": 1,
    },
    {
        "tracking_id": "CE-2026-0003",
        "category": "road",
        "issue_type": "Road Cave-in",
        "description": "Sunken road trench after underground cabling work. Autos bottoming out severely.",
        "address_text": "Ashok Nagar 3rd Cross, Tumakuru",
        "lat": 13.3470, "lng": 77.0988,
        "severity": 5,
        "reasons": ["Trench backfill washed away causing structural road collapse", "Repeatedly reported by 4 residents in same 50m zone"],
        "detected_issue": "Road Cave-in After Trenching",
        "summary": "Severe 20cm trench depression following cable excavation. Impassable for low-clearance vehicles and dangerous for night commuters.",
        "suggested_action": "Excavate sub-base, refill with wet mix macadam (WMM) and bitumen surfacing.",
        "status": "In Progress",
        "days_ago": 8, "res_hours": None,
        "dept_name": "Tumakuru City Corporation - Engineering Wing",
        "report_count": 4, # DUPLICATE CLUSTER 1
    },
    {
        "tracking_id": "CE-2026-0004",
        "category": "road",
        "issue_type": "Road Damage",
        "description": "Unmarked steep speed breaker without paint stripes on flyover service road.",
        "address_text": "Batawadi Flyover Service Road, Tumakuru",
        "lat": 13.3548, "lng": 77.1182,
        "severity": 3,
        "reasons": ["Steep asphalt hump lacks retro-reflective thermoplastic markings", "Skid marks from emergency braking"],
        "detected_issue": "Unmarked Speed Breaker",
        "summary": "Hazardous unpainted speed breaker on Batawadi service road causing frequent vehicular skidding and sudden braking.",
        "suggested_action": "Paint standard IRC chevron marking and install caution signage.",
        "status": "Resolved",
        "days_ago": 16, "res_hours": 14,
        "dept_name": "PWD Tumakuru Division",
        "report_count": 1,
    },
    {
        "tracking_id": "CE-2026-0005",
        "category": "road",
        "issue_type": "Road Damage",
        "description": "Loose aggregate gravel spilled across turning curve causing two-wheeler skids.",
        "address_text": "Ring Road Junction, Near Heggere, Tumakuru",
        "lat": 13.3135, "lng": 77.0862,
        "severity": 4,
        "reasons": ["Loose stone aggregate on turning curve", "Loss of vehicle tire traction on turn"],
        "detected_issue": "Loose Gravel Surface Hazard",
        "summary": "Heavy gravel spill on outer radius of Ring Road curve creating severe skidding hazard for two-wheelers.",
        "suggested_action": "Deploy road sweeper truck and seal asphalt binder coat.",
        "status": "Assigned",
        "days_ago": 5, "res_hours": None,
        "dept_name": "PWD Tumakuru Division",
        "report_count": 1,
    },
    {
        "tracking_id": "CE-2026-0006",
        "category": "road",
        "issue_type": "Road Cave-in",
        "description": "Cast iron drain manhole frame sunk 8cm below road level in heavy traffic lane.",
        "address_text": "Gubbi Gate Main Road, Tumakuru",
        "lat": 13.3418, "lng": 77.0924,
        "severity": 4,
        "reasons": ["Sunken manhole lid creates sharp rim hazard", "High risk of tire burst and wheel rim bending"],
        "detected_issue": "Sunken Manhole Cover",
        "summary": "Drainage manhole frame depressed significantly below pavement surface, jarring vehicles near Gubbi Gate.",
        "suggested_action": "Raise manhole frame with brick masonry collar to flush road grade.",
        "status": "Under Review",
        "days_ago": 3, "res_hours": None,
        "dept_name": "Tumakuru City Corporation - Engineering Wing",
        "report_count": 1,
    },
    {
        "tracking_id": "CE-2026-0007",
        "category": "road",
        "issue_type": "Road Damage",
        "description": "Alligator cracking and edge raveling along canal road shoulder.",
        "address_text": "Maralur Canal Road, Tumakuru",
        "lat": 13.3575, "lng": 77.0790,
        "severity": 2,
        "reasons": ["Surface asphalt cracking along shoulder", "Water seepage weakening sub-base"],
        "detected_issue": "Asphalt Edge Raveling",
        "summary": "Pavement deterioration and edge cracking along Maralur Canal road requiring preventive maintenance.",
        "suggested_action": "Apply asphalt slurry seal and roll compacted gravel along shoulder.",
        "status": "Resolved",
        "days_ago": 28, "res_hours": 48,
        "dept_name": "PWD Tumakuru Division",
        "report_count": 1,
    },
    {
        "tracking_id": "CE-2026-0008",
        "category": "road",
        "issue_type": "Pothole",
        "description": "Cluster of 4 severe potholes on highway pilgrimage stretch near Siddaganga Math.",
        "address_text": "Old NH 4, Near Siddaganga Math Arch, Kyathsandra, Tumakuru",
        "lat": 13.3215, "lng": 77.1575,
        "severity": 5,
        "reasons": ["Multiple deep craters along pilgrimage corridor", "Heavy bus traffic swerving into oncoming lanes", "Reported by 6 different citizens"],
        "detected_issue": "Severe Pothole Cluster on Highway",
        "summary": "Major pothole cluster on old NH 4 near Kyathsandra causing heavy traffic bottlenecks and multiple vehicle axle damage incidents.",
        "suggested_action": "Priority asphalt patching followed by continuous milling and resurfacing.",
        "status": "Resolved",
        "days_ago": 15, "res_hours": 24,
        "dept_name": "PWD Tumakuru Division",
        "report_count": 6, # DUPLICATE CLUSTER 2
    },
    {
        "tracking_id": "CE-2026-0009",
        "category": "road",
        "issue_type": "Road Damage",
        "description": "Concrete median crushed by truck collision with exposed steel rebar.",
        "address_text": "SS Puram Main Road, Near Ganesha Temple, Tumakuru",
        "lat": 13.3365, "lng": 77.1118,
        "severity": 4,
        "reasons": ["Broken concrete barrier spilling onto inner lane", "Protruding steel rods pose tire puncture danger"],
        "detected_issue": "Crushed Median Barrier with Exposed Rebar",
        "summary": "Severe median damage on SS Puram road with sharp exposed rebar posing extreme risk to motorists.",
        "suggested_action": "Cut exposed steel and pour precast concrete divider section.",
        "status": "In Progress",
        "days_ago": 6, "res_hours": None,
        "dept_name": "Tumakuru City Corporation - Engineering Wing",
        "report_count": 1,
    },
    {
        "tracking_id": "CE-2026-0010",
        "category": "road",
        "issue_type": "Broken Curb",
        "description": "Interlocking paver blocks shifted and broken on bus stand footway.",
        "address_text": "Opposite KSRTC Central Bus Stand, Tumakuru",
        "lat": 13.3380, "lng": 77.1045,
        "severity": 2,
        "reasons": ["Uneven pedestrian walkway", "Trip risk for bus commuters"],
        "detected_issue": "Displaced Paver Blocks",
        "summary": "Displaced and damaged paver blocks creating uneven pedestrian footing outside KSRTC bus station.",
        "suggested_action": "Re-level sand bedding and re-lay paver blocks.",
        "status": "Assigned",
        "days_ago": 11, "res_hours": None,
        "dept_name": "Tumakuru City Corporation - Engineering Wing",
        "report_count": 1,
    },
    {
        "tracking_id": "CE-2026-0011",
        "category": "road",
        "issue_type": "Road Damage",
        "description": "Eroded road shoulder creating sharp 12cm drop-off from tar edge.",
        "address_text": "Upparhalli Railway Bridge Road, Tumakuru",
        "lat": 13.3285, "lng": 77.0935,
        "severity": 3,
        "reasons": ["Monsoon rainwater washed gravel away", "Steep drop-off if vehicle wheels leave asphalt"],
        "detected_issue": "Eroded Shoulder Drop-off",
        "summary": "Shoulder erosion along railway bridge approach road creating dangerous edge drop for two-wheelers.",
        "suggested_action": "Grade and compact stone aggregate along 150m shoulder.",
        "status": "Submitted",
        "days_ago": 2, "res_hours": None,
        "dept_name": "Tumakuru City Corporation - Engineering Wing",
        "report_count": 1,
    },
    {
        "tracking_id": "CE-2026-0012",
        "category": "road",
        "issue_type": "Pothole",
        "description": "Large pothole in front of district hospital emergency entrance.",
        "address_text": "District Hospital Road, Jayanagar, Tumakuru",
        "lat": 13.3512, "lng": 77.0955,
        "severity": 4,
        "reasons": ["Jarring impact to ambulances and patients", "Standing water concealing hole depth"],
        "detected_issue": "Hospital Entrance Pothole",
        "summary": "Hazardous pothole right outside District Hospital emergency entrance, impeding rapid ambulance access.",
        "suggested_action": "Priority emergency asphalt patch within 12 hours.",
        "status": "Resolved",
        "days_ago": 12, "res_hours": 8,
        "dept_name": "Tumakuru City Corporation - Engineering Wing",
        "report_count": 1,
    },
    {
        "tracking_id": "CE-2026-0013",
        "category": "road",
        "issue_type": "Road Damage",
        "description": "Transverse crack widening across concrete road pavement.",
        "address_text": "Sapthagiri Extension 1st Main, Tumakuru",
        "lat": 13.3315, "lng": 77.1188,
        "severity": 2,
        "reasons": ["Concrete slab shrinkage crack", "Water infiltration into road foundation"],
        "detected_issue": "Concrete Pavement Joint Crack",
        "summary": "Long transverse crack across residential concrete road in Sapthagiri Extension requiring joint sealant.",
        "suggested_action": "Rout crack groove and fill with elastomeric polyurethane sealant.",
        "status": "Assigned",
        "days_ago": 9, "res_hours": None,
        "dept_name": "Tumakuru City Corporation - Engineering Wing",
        "report_count": 1,
    },
    {
        "tracking_id": "CE-2026-0014",
        "category": "road",
        "issue_type": "Road Cave-in",
        "description": "Culvert stone wingwall collapsed during rain, road embankment undermined.",
        "address_text": "APMC Yard Approach Road, Batawadi, Tumakuru",
        "lat": 13.3590, "lng": 77.1210,
        "severity": 5,
        "reasons": ["Masonry wall collapse undermining road foundation", "High collapse risk under heavy farm tractors"],
        "detected_issue": "Culvert Wingwall Structural Collapse",
        "summary": "Masonry failure on APMC approach culvert with partial roadway subsidence under heavy agricultural transport.",
        "suggested_action": "Construct reinforced concrete retaining wall and backfill road embankment.",
        "status": "In Progress",
        "days_ago": 4, "res_hours": None,
        "dept_name": "PWD Tumakuru Division",
        "report_count": 1,
    },
    {
        "tracking_id": "CE-2026-0015",
        "category": "road",
        "issue_type": "Pothole",
        "description": "Several potholes along school van route near Someshwara Puram school.",
        "address_text": "Someshwara Puram Main Road, Tumakuru",
        "lat": 13.3378, "lng": 77.0875,
        "severity": 3,
        "reasons": ["Multiple road potholes on school route", "Cyclists swerving into traffic"],
        "detected_issue": "School Zone Potholes",
        "summary": "Surface cratering on Someshwara Puram road near high school creating safety concerns during morning drop-off hours.",
        "suggested_action": "Patch and compact with hot asphalt premix.",
        "status": "Under Review",
        "days_ago": 4, "res_hours": None,
        "dept_name": "Tumakuru City Corporation - Engineering Wing",
        "report_count": 1,
    },

    # -------------------------------------------------------------------------
    # POLLUTION & SANITATION COMPLAINTS (13 items)
    # -------------------------------------------------------------------------
    {
        "tracking_id": "CE-2026-0016",
        "category": "pollution",
        "issue_type": "Garbage Dump",
        "description": "Overflowing municipal waste bin spilling organic waste onto road.",
        "address_text": "Gandhi Nagar 4th Cross, Tumakuru",
        "lat": 13.3428, "lng": 77.1068,
        "severity": 3,
        "reasons": ["Uncollected waste overflowing container", "Stray cattle scattering garbage"],
        "detected_issue": "Overflowing Community Garbage Bin",
        "summary": "Large garbage bin overflowing with rotting kitchen waste attracting stray animals and blocking half the roadway.",
        "suggested_action": "Dispatch tipper auto-rickshaw and sanitize container area with bleaching powder.",
        "status": "Resolved",
        "days_ago": 19, "res_hours": 10,
        "dept_name": "Tumakuru City Corporation - Sanitation Wing",
        "report_count": 1,
    },
    {
        "tracking_id": "CE-2026-0017",
        "category": "pollution",
        "issue_type": "Air Pollution",
        "description": "Open burning of dry leaves and plastic waste emitting thick toxic smoke.",
        "address_text": "Shantinagar Park Perimeter, Tumakuru",
        "lat": 13.3492, "lng": 77.1078,
        "severity": 4,
        "reasons": ["Dense toxic smoke near residential colony", "Violation of municipal plastic waste rules"],
        "detected_issue": "Illegal Open Waste Burning",
        "summary": "Uncontrolled burning of dry leaves and plastic packaging along park fence creating heavy choking smoke for local residents.",
        "suggested_action": "Douse fire immediately and issue penalty notice to offenders.",
        "status": "Resolved",
        "days_ago": 14, "res_hours": 7,
        "dept_name": "Karnataka State Pollution Control Board - Tumakuru Office",
        "report_count": 1,
    },
    {
        "tracking_id": "CE-2026-0018",
        "category": "pollution",
        "issue_type": "Garbage Dump",
        "description": "Massive dumping of vegetable and fruit market waste on vacant plot.",
        "address_text": "Mandipet Vegetable Market Backside, Tumakuru",
        "lat": 13.3445, "lng": 77.1035,
        "severity": 5,
        "reasons": ["Over 3 tons of rotting organic waste", "Severe foul odour and fly breeding near food vendors", "Reported by 5 local merchants"],
        "detected_issue": "Massive Illegal Market Waste Dump",
        "summary": "Huge accumulation of decomposing market produce on an unfenced plot in Mandipet creating severe health and sanitation risks.",
        "suggested_action": "Deploy JCB excavator, haul waste to composting site, and erect warning signage.",
        "status": "In Progress",
        "days_ago": 7, "res_hours": None,
        "dept_name": "Tumakuru City Corporation - Sanitation Wing",
        "report_count": 5, # DUPLICATE CLUSTER 3
    },
    {
        "tracking_id": "CE-2026-0019",
        "category": "pollution",
        "issue_type": "Garbage Dump",
        "description": "Construction debris and plaster rubble dumped on public footpath.",
        "address_text": "Ashok Nagar Ring Road Connection, Tumakuru",
        "lat": 13.3465, "lng": 77.0975,
        "severity": 2,
        "reasons": ["Broken concrete blocks blocking pedestrian path", "Pedestrians forced into fast traffic lane"],
        "detected_issue": "Construction & Demolition Debris",
        "summary": "Unclaimed heap of construction rubble obstructing pedestrian access along Ashok Nagar connection road.",
        "suggested_action": "Issue notice to nearby construction site and haul rubble to C&D processing yard.",
        "status": "Assigned",
        "days_ago": 10, "res_hours": None,
        "dept_name": "Tumakuru City Corporation - Sanitation Wing",
        "report_count": 1,
    },
    {
        "tracking_id": "CE-2026-0020",
        "category": "pollution",
        "issue_type": "Air Pollution",
        "description": "Heavy black soot emissions from unregulated bakery chimney.",
        "address_text": "Melekote Industrial Area Road, Tumakuru",
        "lat": 13.3625, "lng": 77.0855,
        "severity": 3,
        "reasons": ["Soot plume below required rooftop height", "Eye irritation reported by nearby workers"],
        "detected_issue": "Unfiltered Industrial Bakery Soot",
        "summary": "Dense chimney emissions from commercial wood-fired bakery blowing particulate matter into adjacent residential buildings.",
        "suggested_action": "KSPCB field inspector to inspect chimney height and scrubbers.",
        "status": "Under Review",
        "days_ago": 5, "res_hours": None,
        "dept_name": "Karnataka State Pollution Control Board - Tumakuru Office",
        "report_count": 1,
    },
    {
        "tracking_id": "CE-2026-0021",
        "category": "pollution",
        "issue_type": "Garbage Dump",
        "description": "Butcher shop waste and animal bones dumped along stormwater channel.",
        "address_text": "Kyathsandra Old Toll Gate, Tumakuru",
        "lat": 13.3225, "lng": 77.1568,
        "severity": 4,
        "reasons": ["Putrefying animal waste near open water drain", "Extreme biohazard and odour"],
        "detected_issue": "Rotting Abattoir Waste in Drain",
        "summary": "Illegal dumping of slaughterhouse waste in open stormwater drain near Kyathsandra causing nauseating smell and fly infestation.",
        "suggested_action": "Emergency bio-cleanup and apply lime/bleach disinfectant.",
        "status": "Resolved",
        "days_ago": 23, "res_hours": 12,
        "dept_name": "Tumakuru City Corporation - Sanitation Wing",
        "report_count": 1,
    },
    {
        "tracking_id": "CE-2026-0022",
        "category": "pollution",
        "issue_type": "Garbage Dump",
        "description": "Accumulation of plastic bottles and snack pouches along lake walking track.",
        "address_text": "Amanikere Lake Promenade, Tumakuru",
        "lat": 13.3435, "lng": 77.1150,
        "severity": 2,
        "reasons": ["Littering along public recreation area", "Plastic blowing into lake waters"],
        "detected_issue": "Lakefront Plastic Litter",
        "summary": "Extensive plastic litter along the Amanikere Lake walkway following weekend crowds.",
        "suggested_action": "Organize sanitation sweep and install 4 twin-litter bins.",
        "status": "Resolved",
        "days_ago": 20, "res_hours": 24,
        "dept_name": "Tumakuru City Corporation - Sanitation Wing",
        "report_count": 1,
    },
    {
        "tracking_id": "CE-2026-0023",
        "category": "pollution",
        "issue_type": "Industrial Waste",
        "description": "Chemical effluent discharge creating green foam in public stormwater gutter.",
        "address_text": "Antharasanahalli Industrial Layout, Tumakuru",
        "lat": 13.3680, "lng": 77.1040,
        "severity": 5,
        "reasons": ["Frothing chemical discharge into public drain", "Vegetation dead within 20m downstream", "High toxicity hazard"],
        "detected_issue": "Untreated Industrial Effluent Discharge",
        "summary": "Unauthorized discharge of untreated chemical wash water from industrial unit causing chemical stench and heavy frothing in Antharasanahalli.",
        "suggested_action": "Collect water samples for lab testing and issue immediate stop-work notice.",
        "status": "In Progress",
        "days_ago": 5, "res_hours": None,
        "dept_name": "Karnataka State Pollution Control Board - Tumakuru Office",
        "report_count": 1,
    },
    {
        "tracking_id": "CE-2026-0024",
        "category": "pollution",
        "issue_type": "Garbage Dump",
        "description": "Door-to-door garbage truck missed street for 4 days, waste bags piled on corner.",
        "address_text": "Vivekananda Nagar 2nd Main, Tumakuru",
        "lat": 13.3485, "lng": 77.1135,
        "severity": 2,
        "reasons": ["Domestic waste accumulated for 4 days", "Flies and dog scavenging"],
        "detected_issue": "Missed Municipal Waste Collection",
        "summary": "Garbage pile on Vivekananda Nagar street corner due to missed garbage auto-tipper collection over the weekend.",
        "suggested_action": "Reroute morning collection vehicle and clear backlog.",
        "status": "Resolved",
        "days_ago": 13, "res_hours": 16,
        "dept_name": "Tumakuru City Corporation - Sanitation Wing",
        "report_count": 1,
    },
    {
        "tracking_id": "CE-2026-0025",
        "category": "pollution",
        "issue_type": "Noise Pollution",
        "description": "Commercial event playing high-decibel loudspeakers past 11 PM near court complex.",
        "address_text": "Near District Court Complex, Tumakuru",
        "lat": 13.3402, "lng": 77.0990,
        "severity": 3,
        "reasons": ["Decibel levels over 85dB past permitted 10 PM limit", "Silence zone violation near judicial quarters"],
        "detected_issue": "Late Night Noise Pollution",
        "summary": "Excessive loudspeaker noise past midnight in silence zone near District Court violating environmental noise rules.",
        "suggested_action": "Municipal enforcement squad to confiscate sound equipment and fine organizers.",
        "status": "Submitted",
        "days_ago": 1, "res_hours": None,
        "dept_name": "Karnataka State Pollution Control Board - Tumakuru Office",
        "report_count": 1,
    },
    {
        "tracking_id": "CE-2026-0026",
        "category": "pollution",
        "issue_type": "Garbage Dump",
        "description": "Stagnant sludge and single-use plastic blocking open canal flow.",
        "address_text": "Upparhalli Main Road Canal, Tumakuru",
        "lat": 13.3290, "lng": 77.0945,
        "severity": 3,
        "reasons": ["Thermocol and packaging choking canal", "High mosquito larvae breeding density"],
        "detected_issue": "Plastic Waste Canal Choke",
        "summary": "Open drainage canal in Upparhalli choked with plastic bags and thermocol, holding stagnant foul water.",
        "suggested_action": "Desilt canal section and apply anti-larval mosquito oil.",
        "status": "In Progress",
        "days_ago": 7, "res_hours": None,
        "dept_name": "Tumakuru City Corporation - Sanitation Wing",
        "report_count": 1,
    },
    {
        "tracking_id": "CE-2026-0027",
        "category": "pollution",
        "issue_type": "Hazardous Waste",
        "description": "Used syringes, needles and medical bandages found dumped in public garbage bin.",
        "address_text": "Near Private Nursing Home, Jayanagar, Tumakuru",
        "lat": 13.3520, "lng": 77.0960,
        "severity": 5,
        "reasons": ["Untreated medical waste in municipal bin", "Infection risk for waste collectors", "Violation of Bio-Medical Waste Rules"],
        "detected_issue": "Illegal Biomedical Waste Disposal",
        "summary": "Hazardous biomedical waste including sharps and bloody cotton swabs dumped improperly in open municipal container in Jayanagar.",
        "suggested_action": "Biohazard team to segregate and incinerate; penalize healthcare facility.",
        "status": "Submitted",
        "days_ago": 1, "res_hours": None,
        "dept_name": "Karnataka State Pollution Control Board - Tumakuru Office",
        "report_count": 1,
    },
    {
        "tracking_id": "CE-2026-0028",
        "category": "pollution",
        "issue_type": "Air Pollution",
        "description": "Wood dust from timber sawmill blowing across roadway without dust barrier.",
        "address_text": "Batawadi Industrial Road, Tumakuru",
        "lat": 13.3560, "lng": 77.1170,
        "severity": 3,
        "reasons": ["Airborne particulate wood dust", "Respiratory irritation for two-wheeler commuters"],
        "detected_issue": "Airborne Wood Dust Pollution",
        "summary": "Unenclosed timber sawing operations blowing dense clouds of wood particles over Batawadi Industrial Road.",
        "suggested_action": "Mandate installation of cyclone dust collectors and water sprayers.",
        "status": "Under Review",
        "days_ago": 3, "res_hours": None,
        "dept_name": "Karnataka State Pollution Control Board - Tumakuru Office",
        "report_count": 1,
    },

    # -------------------------------------------------------------------------
    # WATER & SEWAGE COMPLAINTS (12 items)
    # -------------------------------------------------------------------------
    {
        "tracking_id": "CE-2026-0029",
        "category": "water",
        "issue_type": "Water Leakage",
        "description": "High pressure drinking water pipeline burst gushing clean water down street.",
        "address_text": "SIT Extension 5th Cross, Tumakuru",
        "lat": 13.3295, "lng": 77.1245,
        "severity": 4,
        "reasons": ["Pressurized potable water main fracture", "Large scale drinking water wastage"],
        "detected_issue": "Burst Potable Water Pipeline",
        "summary": "Underground drinking water main ruptured on SIT 5th cross, sending a 2-foot geyser onto the carriageway.",
        "suggested_action": "Shut isolating valve, excavate break, and clamp with split collar sleeve.",
        "status": "Resolved",
        "days_ago": 25, "res_hours": 15,
        "dept_name": "Tumakuru City Corporation - Water Supply",
        "report_count": 1,
    },
    {
        "tracking_id": "CE-2026-0030",
        "category": "water",
        "issue_type": "Sewage Overflow",
        "description": "Choked underground sewer overflowing dark foul sewage into residential compounds.",
        "address_text": "SS Puram 7th Cross, Tumakuru",
        "lat": 13.3355, "lng": 77.1125,
        "severity": 5,
        "reasons": ["Sewer line blockage causing sewage backflow", "Flooding 3 residential gates with contaminated water", "Reported by 3 neighbouring families"],
        "detected_issue": "Choked Sewer Chamber Overflow",
        "summary": "Main underground sewer choked with silt and grease, overflowing raw black sewage across SS Puram 7th Cross roadway and gates.",
        "suggested_action": "Deploy super-sucker jetting machine to clear sewer line blockage.",
        "status": "In Progress",
        "days_ago": 3, "res_hours": None,
        "dept_name": "KUWS&DB Tumakuru",
        "report_count": 3, # DUPLICATE CLUSTER 4
    },
    {
        "tracking_id": "CE-2026-0031",
        "category": "water",
        "issue_type": "Contaminated Water",
        "description": "Brown turbid tap water with foul sewage smell coming from kitchen taps.",
        "address_text": "Ashok Nagar 1st Main, Tumakuru",
        "lat": 13.3458, "lng": 77.0995,
        "severity": 5,
        "reasons": ["Tap water visibly brown and smelling of sewage", "Sub-surface cross-contamination suspected"],
        "detected_issue": "Drinking Water Contamination",
        "summary": "Severe drinking water contamination in Ashok Nagar with tap supply discoloured and smelling of sewage cross-leakage.",
        "suggested_action": "Flush pipeline, identify cross-leak, and supply emergency drinking water tanker.",
        "status": "Resolved",
        "days_ago": 18, "res_hours": 22,
        "dept_name": "Tumakuru City Corporation - Water Supply",
        "report_count": 1,
    },
    {
        "tracking_id": "CE-2026-0032",
        "category": "water",
        "issue_type": "Low Water Pressure",
        "description": "Entire street receiving almost zero water pressure for past 5 days.",
        "address_text": "Vidyanagar 4th Cross, Tumakuru",
        "lat": 13.3325, "lng": 77.1315,
        "severity": 3,
        "reasons": ["Piped water supply trickling or dry", "Air lock suspected in distribution branch line"],
        "detected_issue": "Low Municipal Water Pressure",
        "summary": "Acute lack of water pressure across Vidyanagar 4th Cross leaving 20+ households dependent on private water tankers.",
        "suggested_action": "Operate air release valves and test branch line pressure.",
        "status": "Resolved",
        "days_ago": 11, "res_hours": 42,
        "dept_name": "Tumakuru City Corporation - Water Supply",
        "report_count": 1,
    },
    {
        "tracking_id": "CE-2026-0033",
        "category": "water",
        "issue_type": "Water Leakage",
        "description": "Sluice valve gland packing leaking constantly into open storm drain.",
        "address_text": "B.H. Road Near Railway Station, Tumakuru",
        "lat": 13.3405, "lng": 77.1008,
        "severity": 2,
        "reasons": ["Worn valve seal leaking clean water", "Continuous trickle into drain"],
        "detected_issue": "Leaking Sluice Valve Gland",
        "summary": "Water distribution valve leaking steadily near Tumakuru railway station, wasting treated potable water.",
        "suggested_action": "Replace gland packing and lubricate valve stem.",
        "status": "Assigned",
        "days_ago": 8, "res_hours": None,
        "dept_name": "KUWS&DB Tumakuru",
        "report_count": 1,
    },
    {
        "tracking_id": "CE-2026-0034",
        "category": "water",
        "issue_type": "Sewage Overflow",
        "description": "Heavy vehicle smashed concrete slab cover of 6-foot deep stormwater drain.",
        "address_text": "Gandhi Nagar Main Road, Tumakuru",
        "lat": 13.3420, "lng": 77.1055,
        "severity": 4,
        "reasons": ["Open 6-foot drain abyss right on footpath", "Immediate danger of pedestrians falling in at night"],
        "detected_issue": "Broken Storm Drain Cover Slab",
        "summary": "Cracked and collapsed drain cover slab on busy Gandhi Nagar pedestrian route creating critical open hole hazard.",
        "suggested_action": "Install heavy-duty reinforced precast concrete slab cover.",
        "status": "Resolved",
        "days_ago": 27, "res_hours": 14,
        "dept_name": "Tumakuru City Corporation - Water Supply",
        "report_count": 1,
    },
    {
        "tracking_id": "CE-2026-0035",
        "category": "water",
        "issue_type": "Drainage Issue",
        "description": "Blocked culvert under railway bridge causing 1.5ft water ponding after rain.",
        "address_text": "Batawadi Ring Road Underpass, Tumakuru",
        "lat": 13.3540, "lng": 77.1195,
        "severity": 4,
        "reasons": ["Underpass culvert clogged with silt", "Stalling auto-rickshaws and two-wheelers"],
        "detected_issue": "Underpass Stormwater Flooding",
        "summary": "Heavy waterlogging under Batawadi rail bridge due to choked drainage siphon, halting city transit.",
        "suggested_action": "Clear sediment with mechanical backhoe and restore gravity flow.",
        "status": "Resolved",
        "days_ago": 21, "res_hours": 18,
        "dept_name": "KUWS&DB Tumakuru",
        "report_count": 1,
    },
    {
        "tracking_id": "CE-2026-0036",
        "category": "water",
        "issue_type": "Sewage Overflow",
        "description": "Underground sewer leak seeping through ground and softening compound wall foundation.",
        "address_text": "Shantinagar 5th Cross, Tumakuru",
        "lat": 13.3488, "lng": 77.1090,
        "severity": 3,
        "reasons": ["Constant underground sewage leak", "Structural weakening of residential boundary wall"],
        "detected_issue": "Subsurface Sewer Seepage",
        "summary": "Subterranean sewer pipe leak causing soggy soil and structural tilt in boundary wall in Shantinagar.",
        "suggested_action": "Excavate and replace cracked clay sewer pipe with PVC.",
        "status": "In Progress",
        "days_ago": 9, "res_hours": None,
        "dept_name": "KUWS&DB Tumakuru",
        "report_count": 1,
    },
    {
        "tracking_id": "CE-2026-0037",
        "category": "water",
        "issue_type": "Water Leakage",
        "description": "Vandalized brass tap on public water standpost continuously running.",
        "address_text": "Mandipet Bus Stop, Tumakuru",
        "lat": 13.3448, "lng": 77.1025,
        "severity": 2,
        "reasons": ["Broken tap head cannot be shut off", "Clean water pooling across bus boarding area"],
        "detected_issue": "Broken Public Standpost Tap",
        "summary": "Continuous flow from damaged public drinking tap near Mandipet bus shelter causing water wastage.",
        "suggested_action": "Install push-button self-closing tap valve.",
        "status": "Submitted",
        "days_ago": 2, "res_hours": None,
        "dept_name": "Tumakuru City Corporation - Water Supply",
        "report_count": 1,
    },
    {
        "tracking_id": "CE-2026-0038",
        "category": "water",
        "issue_type": "Sewage Overflow",
        "description": "Main street sewer blocked causing reverse flow of toilet sewage into basement floor.",
        "address_text": "Jayanagar 2nd Cross, Tumakuru",
        "lat": 13.3505, "lng": 77.0940,
        "severity": 5,
        "reasons": ["Severe sewer blockage causing back pressure", "Raw sewage entering building basement floor", "Extreme health emergency"],
        "detected_issue": "Main Sewer Backflow Emergency",
        "summary": "Emergency sewer backflow into lower level residence on Jayanagar 2nd cross caused by downstream sewer collapse.",
        "suggested_action": "Reroute sewage via bypass pump and jet main collector line.",
        "status": "Under Review",
        "days_ago": 2, "res_hours": None,
        "dept_name": "KUWS&DB Tumakuru",
        "report_count": 1,
    },
    {
        "tracking_id": "CE-2026-0039",
        "category": "water",
        "issue_type": "Drainage Issue",
        "description": "Gutter built with negative slope holds stagnant dirty water year round.",
        "address_text": "Someshwara Puram 4th Cross, Tumakuru",
        "lat": 13.3372, "lng": 77.0882,
        "severity": 2,
        "reasons": ["Inadequate drainage slope", "Foul water pool breeding mosquitoes"],
        "detected_issue": "Negative Gradient Drain Stagnation",
        "summary": "Stagnant drainage pool along Someshwara Puram 4th Cross due to faulty cement drain grading.",
        "suggested_action": "Re-grade concrete gutter bed with 1:200 slope.",
        "status": "Submitted",
        "days_ago": 1, "res_hours": None,
        "dept_name": "Tumakuru City Corporation - Water Supply",
        "report_count": 1,
    },
    {
        "tracking_id": "CE-2026-0040",
        "category": "water",
        "issue_type": "Water Leakage",
        "description": "Underground borewell pipe fracture bubbling water through street asphalt.",
        "address_text": "Melekote Residential Area, Tumakuru",
        "lat": 13.3615, "lng": 77.0845,
        "severity": 3,
        "reasons": ["Pressurized borewell delivery leak", "Softening road asphalt from underneath"],
        "detected_issue": "Underground Borewell Pipe Leak",
        "summary": "Borewell delivery line leak in Melekote pushing pressurized water through road cracks.",
        "suggested_action": "Dig trench and weld galvanized iron riser joint.",
        "status": "In Progress",
        "days_ago": 6, "res_hours": None,
        "dept_name": "Tumakuru City Corporation - Water Supply",
        "report_count": 1,
    },
]


def seed_complaints():
    """
    Seeds the database with 40 deterministic sample complaints for Tumakuru.
    Only called if Complaint table is empty.
    """
    # Import models locally from app to avoid circular import
    from app import db, Complaint, Department, StatusHistory

    # Safety check: only seed if empty
    if Complaint.query.count() > 0:
        print("Complaint table already populated; skipping seed.")
        return

    # Cache departments by name
    all_depts = {d.name: d for d in Department.query.all()}

    # Gather available seed photos per category (skips gracefully if folder is empty)
    road_photos = get_seed_photos("road")
    pollution_photos = get_seed_photos("pollution")
    water_photos = get_seed_photos("water")
    after_photos = get_seed_photos("after")

    category_photo_map = {
        "road": road_photos,
        "pollution": pollution_photos,
        "water": water_photos,
    }

    # Deterministic base timestamp:
    # Use an anchor relative to current time so all items fall cleanly within the last 30 days
    now = datetime.now(timezone.utc)

    road_photo_idx = 0
    poll_photo_idx = 0
    water_photo_idx = 0
    after_photo_idx = 0

    seeded_complaints = []
    status_histories = []

    for item in SEED_ITEMS:
        cat = item["category"]
        dept = all_depts.get(item["dept_name"])
        dept_id = dept.id if dept else None

        # Pick photo from static/seed/<category>/ if available
        photo_path = None
        available_photos = category_photo_map.get(cat, [])
        if available_photos:
            if cat == "road":
                photo_path = available_photos[road_photo_idx % len(available_photos)]
                road_photo_idx += 1
            elif cat == "pollution":
                photo_path = available_photos[poll_photo_idx % len(available_photos)]
                poll_photo_idx += 1
            elif cat == "water":
                photo_path = available_photos[water_photo_idx % len(available_photos)]
                water_photo_idx += 1

        # For Resolved road complaints, pick from static/seed/after/ if available
        after_photo_path = None
        if item["status"] == "Resolved" and cat == "road" and after_photos:
            after_photo_path = after_photos[after_photo_idx % len(after_photos)]
            after_photo_idx += 1

        # Deterministic created_at timestamp spread over last 30 days
        created_dt = now - timedelta(days=item["days_ago"], hours=(item["severity"] * 3) % 12)

        fix_verified = True if (item["status"] == "Resolved" and after_photo_path) else None
        fix_note = (
            f"Municipal repair completed; {item['detected_issue'].lower()} verified fixed."
            if (item["status"] == "Resolved" and after_photo_path)
            else ("Resolved via field team closure (Pending verification)." if item["status"] == "Resolved" else None)
        )

        complaint = Complaint(
            tracking_id=item["tracking_id"],
            category=cat,
            issue_type=item["issue_type"],
            description=item["description"],
            photo_path=photo_path,
            after_photo_path=after_photo_path,
            fix_verified=fix_verified,
            fix_note=fix_note,
            audio_path=None,  # Public privacy requirement
            transcription=None,
            latitude=item["lat"],
            longitude=item["lng"],
            address_text=item["address_text"],
            status=item["status"],
            severity=item["severity"],
            severity_reasons=json.dumps(item["reasons"]),
            ai_summary=item["summary"],
            detected_issue=item["detected_issue"],
            suggested_action=item["suggested_action"],
            ai_source="seed",
            ai_confidence=0.92,
            image_matches_report=True,
            parent_id=None,
            report_count=item["report_count"],
            department_id=dept_id,
            created_at=created_dt,
        )
        seeded_complaints.append(complaint)

    # Flush complaints to get valid IDs for StatusHistory
    db.session.add_all(seeded_complaints)
    db.session.flush()

    # Create matching StatusHistory rows for each complaint
    for complaint, item in zip(seeded_complaints, SEED_ITEMS):
        created_dt = complaint.created_at
        status = item["status"]

        # Step 1: Initial submission
        sh_submitted = StatusHistory(
            complaint_id=complaint.id,
            status="Submitted",
            note="Grievance registered in CivicEye portal",
            changed_at=created_dt
        )
        status_histories.append(sh_submitted)

        # Step 2: Under Review (if reached)
        if status in ["Under Review", "Assigned", "In Progress", "Resolved"]:
            review_time = created_dt + timedelta(hours=2, minutes=15)
            sh_review = StatusHistory(
                complaint_id=complaint.id,
                status="Under Review",
                note="Triage review completed by municipal operations desk",
                changed_at=review_time
            )
            status_histories.append(sh_review)

        # Step 3: Assigned (if reached)
        if status in ["Assigned", "In Progress", "Resolved"]:
            dept_name = item["dept_name"]
            assigned_time = created_dt + timedelta(hours=5, minutes=30)
            sh_assigned = StatusHistory(
                complaint_id=complaint.id,
                status="Assigned",
                note=f"Assigned to {dept_name} for field inspection",
                changed_at=assigned_time
            )
            status_histories.append(sh_assigned)

        # Step 4: In Progress (if reached)
        if status in ["In Progress", "Resolved"]:
            progress_time = created_dt + timedelta(hours=11, minutes=45)
            sh_progress = StatusHistory(
                complaint_id=complaint.id,
                status="In Progress",
                note="Field maintenance crew dispatched to site",
                changed_at=progress_time
            )
            status_histories.append(sh_progress)

        # Step 5: Resolved (if reached, with believable resolution time between 6h and 6 days)
        if status == "Resolved":
            res_hours = item["res_hours"] or 24
            resolved_time = created_dt + timedelta(hours=res_hours)
            sh_resolved = StatusHistory(
                complaint_id=complaint.id,
                status="Resolved",
                note="Field work verified and certified resolved by municipal engineering supervisor",
                changed_at=resolved_time
            )
            status_histories.append(sh_resolved)

    db.session.add_all(status_histories)
    db.session.commit()
    print(f"Successfully seeded {len(seeded_complaints)} sample complaints and {len(status_histories)} status history rows.")


if __name__ == "__main__":
    from app import app
    with app.app_context():
        seed_complaints()
