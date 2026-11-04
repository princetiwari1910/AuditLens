import type { Template } from "../api/types";

export const DEFAULT_TEMPLATES: Template[] = [
  {
    "id": "campus_fire_exit_core",
    "name": "Campus Fire Exit Core (Phone Walkthrough)",
    "description": "Core 4-rule phone walkthrough audit for campus corridors and labs. Verifies visible extinguishers, illuminated exit signage, unobstructed exit paths, and clear extinguisher access without requiring optical scale measurements.",
    "disclaimer": "AuditLens is an assistive pre-audit tool. It does not certify legal compliance. Verify against institutional safety standards and local fire codes.",
    "rules": [
      {
        "id": "extinguisher_visible",
        "title": "Fire extinguisher is mounted and clearly visible",
        "type": "presence",
        "severity": "high",
        "detector": "SAM 3.1 (Segmenter)",
        "evidence_needed": "Visual segmentation mask, confidence >= 0.60, timestamp citation",
        "concepts": [
          "fire extinguisher",
          "red fire extinguisher",
          "fire safety canister"
        ],
        "sam_prompts": [
          "fire extinguisher",
          "red fire extinguisher",
          "fire safety canister"
        ],
        "min_confidence": 0.6,
        "params": {
          "min_score": 0.6
        },
        "fix_text": "Mount a certified fire extinguisher on the wall in a prominent, unobstructed location."
      },
      {
        "id": "exit_sign_visible",
        "title": "Emergency exit sign is clearly visible above doorways",
        "type": "presence",
        "severity": "high",
        "detector": "SAM 3.1 (Segmenter)",
        "evidence_needed": "Illuminated green/red exit signage detected above egress doorways",
        "concepts": [
          "emergency exit sign",
          "illuminated exit sign",
          "green exit sign"
        ],
        "sam_prompts": [
          "emergency exit sign",
          "illuminated exit sign",
          "green exit sign"
        ],
        "min_confidence": 0.6,
        "params": {
          "min_score": 0.6
        },
        "fix_text": "Ensure all emergency exit signage is clearly visible and unobstructed."
      },
      {
        "id": "exit_path_not_blocked",
        "title": "Exit corridor and doorway are free of blocking obstacles",
        "type": "absence",
        "severity": "high",
        "detector": "SAM 3.1 (Segmenter)",
        "evidence_needed": "Absence of boxes, carts, furniture, or debris directly obstructing egress",
        "concepts": [
          "storage box",
          "wooden pallet",
          "rolling cart"
        ],
        "sam_prompts": [
          "storage box",
          "wooden pallet",
          "rolling cart"
        ],
        "min_confidence": 0.6,
        "params": {
          "threshold": 0.6
        },
        "fix_text": "Immediately relocate all obstacles, boxes, and furniture blocking the exit doorway or path."
      },
      {
        "id": "extinguisher_accessible",
        "title": "Area in front of fire extinguisher is clear and accessible",
        "type": "absence",
        "severity": "high",
        "detector": "SAM 3.1 (Segmenter)",
        "evidence_needed": "Absence of obstructing storage or items directly in front of the extinguisher",
        "concepts": [
          "storage box",
          "trash can",
          "rolling cart"
        ],
        "sam_prompts": [
          "storage box",
          "trash can",
          "rolling cart"
        ],
        "min_confidence": 0.6,
        "params": {
          "threshold": 0.6
        },
        "fix_text": "Maintain a clear access radius of at least 1 meter around the fire extinguisher."
      }
    ]
  },
  {
    "id": "college_lab_safety",
    "name": "College Lab Fire & Chemical Safety",
    "description": "Comprehensive safety audit for academic chemistry, biology, and engineering labs covering extinguishers, eyewash stations, exit paths, and chemical storage.",
    "disclaimer": "AuditLens is an assistive pre-audit tool. It does not certify legal compliance. Verify against institutional EHS guidelines and local regulations.",
    "rules": [
      {
        "id": "extinguisher_visible",
        "title": "Fire extinguisher is mounted and clearly visible",
        "type": "presence",
        "severity": "high",
        "detector": "SAM 3.1 (Segmenter)",
        "evidence_needed": "Visual segmentation mask, confidence >= 0.60, timestamp citation",
        "sam_prompts": [
          "fire extinguisher",
          "extinguisher"
        ],
        "params": {
          "min_score": 0.6
        },
        "fix_text": "Mount a certified Class ABC or CO2 extinguisher on the wall within 10 meters of chemical workstations."
      },
      {
        "id": "exit_sign_visible",
        "title": "Emergency exit sign is illuminated and clearly visible",
        "type": "presence",
        "severity": "high",
        "detector": "SAM 3.1 (Segmenter)",
        "evidence_needed": "Illuminated green/red exit signage detected above all egress doorways",
        "sam_prompts": [
          "emergency exit sign",
          "exit sign",
          "green running man sign"
        ],
        "params": {
          "min_score": 0.6
        },
        "fix_text": "Install or restore emergency illumination on all lab exit path signs."
      },
      {
        "id": "exit_path_not_blocked",
        "title": "Walkways and fume hood perimeters are free of blocking obstacles",
        "type": "absence",
        "severity": "high",
        "detector": "SAM 3.1 (Segmenter)",
        "evidence_needed": "Absence of boxes, carts, chairs, or chemical containers along the primary walkway",
        "sam_prompts": [
          "box",
          "cart",
          "trash bin",
          "chair",
          "chemical jug",
          "pallet"
        ],
        "params": {
          "threshold": 0.6
        },
        "fix_text": "Immediately clear all lab carts, temporary boxes, and waste containers from main evacuation aisles."
      },
      {
        "id": "exit_path_clear_width",
        "title": "Lab egress aisle maintains minimum clear width of 1.0 meter",
        "type": "measurement",
        "severity": "high",
        "detector": "SAM 3.1 + Optical Calibrator",
        "evidence_needed": "Optical measurement >= 1.0m calibrated via A4 visual scale",
        "sam_prompts": [
          "box",
          "chair",
          "stool",
          "equipment"
        ],
        "params": {
          "min_width_m": 1.0,
          "reference": "a4"
        },
        "fix_text": "Reposition mobile benches and lab stools so at least 1.0m of clear walking width remains."
      },
      {
        "id": "eyewash_station_clear",
        "title": "Emergency eyewash station is unobstructed and visible",
        "type": "presence",
        "severity": "high",
        "detector": "SAM 3.1 (Segmenter)",
        "evidence_needed": "Eyewash station detected with zero obstacles within 1.0m approach",
        "sam_prompts": [
          "eyewash station",
          "safety shower",
          "emergency wash"
        ],
        "params": {
          "min_score": 0.55
        },
        "fix_text": "Clear any glassware, chemical bottles, or drying racks stored within 1 meter of the eyewash station."
      }
    ]
  },
  {
    "id": "fire_exit_safety",
    "name": "Fire & Emergency Exit Safety",
    "description": "Inspects emergency exits, extinguisher readiness, signage, path blockages, and walkway clearance width.",
    "disclaimer": "AuditLens is an assistive pre-audit tool. It does not certify legal compliance. Verify against local regulations and a qualified inspector.",
    "rules": [
      {
        "id": "extinguisher_visible",
        "title": "Fire extinguisher is mounted and clearly visible",
        "type": "presence",
        "severity": "high",
        "detector": "SAM 3.1 (Segmenter)",
        "evidence_needed": "Visual segmentation mask, confidence >= 0.60, timestamp citation",
        "sam_prompts": [
          "fire extinguisher",
          "extinguisher"
        ],
        "params": {
          "min_score": 0.6
        },
        "fix_text": "Install or relocate a certified fire extinguisher to an unobstructed, clearly marked wall mount."
      },
      {
        "id": "exit_sign_visible",
        "title": "Emergency exit sign is illuminated and clearly visible",
        "type": "presence",
        "severity": "high",
        "detector": "SAM 3.1 (Segmenter)",
        "evidence_needed": "Overhead illuminated exit signage detection above doorway",
        "sam_prompts": [
          "emergency exit sign",
          "exit sign",
          "green running man sign"
        ],
        "params": {
          "min_score": 0.6
        },
        "fix_text": "Ensure emergency exit signs are illuminated, unobstructed, and positioned above all exit doors."
      },
      {
        "id": "two_exits_visible",
        "title": "At least two independent emergency exit pathways are visible",
        "type": "count",
        "severity": "medium",
        "detector": "SAM 3.1 (Segmenter)",
        "evidence_needed": "Minimum distinct count of 2 exits de-duplicated across time and position",
        "sam_prompts": [
          "exit door",
          "emergency exit",
          "fire door"
        ],
        "params": {
          "min_count": 2,
          "min_score": 0.55
        },
        "fix_text": "Designate and clearly mark a secondary emergency exit path conforming to occupant capacity requirements."
      },
      {
        "id": "exit_path_not_blocked",
        "title": "Emergency exit corridors and doors are free of blocking obstacles",
        "type": "absence",
        "severity": "high",
        "detector": "SAM 3.1 (Segmenter)",
        "evidence_needed": "Absence of blocking obstacle detections within designated exit zone",
        "sam_prompts": [
          "box",
          "pallet",
          "trash bin",
          "furniture",
          "ladder"
        ],
        "params": {
          "threshold": 0.6
        },
        "fix_text": "Immediately remove all boxes, pallets, and temporary storage from designated exit routes."
      },
      {
        "id": "exit_path_clear_width",
        "title": "Emergency exit path maintains minimum clear width of 1.0 meter",
        "type": "measurement",
        "severity": "high",
        "detector": "SAM 3.1 + Optical Calibrator",
        "evidence_needed": "Optical clearance measurement >= 1.0m relative to calibrated visual scale",
        "sam_prompts": [
          "box",
          "chair",
          "cable",
          "obstruction"
        ],
        "params": {
          "min_width_m": 1.0,
          "reference": "a4"
        },
        "fix_text": "Reorganize stored items and furniture so at least 1.0 m clear walkway width is continuously preserved."
      }
    ]
  },
  {
    "id": "hostel_fire_safety",
    "name": "Hostel & Dormitory Fire Safety",
    "description": "Routine safety audit for student hostels and residential dormitories checking corridor clearance, fire extinguishers, emergency stairwells, and exit doors.",
    "disclaimer": "AuditLens is an assistive pre-audit tool. It does not certify legal compliance. Verify against institutional dormitory regulations and local fire codes.",
    "rules": [
      {
        "id": "extinguisher_visible",
        "title": "Corridor fire extinguisher is accessible and unblocked",
        "type": "presence",
        "severity": "high",
        "detector": "SAM 3.1 (Segmenter)",
        "evidence_needed": "Visual segmentation mask, confidence >= 0.60, timestamp citation",
        "sam_prompts": [
          "fire extinguisher",
          "extinguisher"
        ],
        "params": {
          "min_score": 0.6
        },
        "fix_text": "Verify fire extinguisher pressure gauge and clear all laundry bags or drying racks from its front clearance area."
      },
      {
        "id": "exit_sign_visible",
        "title": "Stairwell fire exit sign is clearly visible",
        "type": "presence",
        "severity": "high",
        "detector": "SAM 3.1 (Segmenter)",
        "evidence_needed": "Overhead illuminated directional exit sign leading toward stairwell",
        "sam_prompts": [
          "emergency exit sign",
          "exit sign",
          "fire exit sign"
        ],
        "params": {
          "min_score": 0.6
        },
        "fix_text": "Replace damaged or unlit stairwell exit signs and verify emergency battery backup functionality."
      },
      {
        "id": "exit_path_not_blocked",
        "title": "Hostel hallway is free of blocking shoe racks, luggage, and bikes",
        "type": "absence",
        "severity": "high",
        "detector": "SAM 3.1 (Segmenter)",
        "evidence_needed": "Absence of shoe racks, trunks, luggage, mattresses, or bikes in the corridor",
        "sam_prompts": [
          "shoe rack",
          "shoes",
          "luggage",
          "box",
          "bicycle",
          "mattress",
          "trash bin"
        ],
        "params": {
          "threshold": 0.6
        },
        "fix_text": "Remove all shoe racks, personal storage, and bicycles obstructing the dormitory corridor."
      },
      {
        "id": "exit_path_clear_width",
        "title": "Corridor maintains minimum clear egress width of 1.2 meters",
        "type": "measurement",
        "severity": "high",
        "detector": "SAM 3.1 + Optical Calibrator",
        "evidence_needed": "Optical measurement >= 1.2m calibrated via A4 visual scale",
        "sam_prompts": [
          "shoe rack",
          "box",
          "bag",
          "luggage"
        ],
        "params": {
          "min_width_m": 1.2,
          "reference": "a4"
        },
        "fix_text": "Ensure corridor width remains unobstructed to a minimum of 1.2 meters along the full length of the hall."
      },
      {
        "id": "two_exits_visible",
        "title": "At least two independent stairwell egress routes are available",
        "type": "count",
        "severity": "medium",
        "detector": "SAM 3.1 (Segmenter)",
        "evidence_needed": "Minimum distinct count of 2 stairwell or external exit doors",
        "sam_prompts": [
          "fire exit door",
          "exit door",
          "stairwell door"
        ],
        "params": {
          "min_count": 2,
          "min_score": 0.55
        },
        "fix_text": "Ensure both ends of the dormitory wing have accessible, unblocked stairwell access."
      }
    ]
  },
  {
    "id": "workshop_ppe",
    "name": "Workshop PPE & General Safety",
    "description": "Verifies mandatory personal protective equipment, first aid station availability, floor cleanliness, and cable hazards.",
    "disclaimer": "AuditLens is an assistive pre-audit tool. It does not certify legal compliance. Verify against local regulations and a qualified inspector.",
    "rules": [
      {
        "id": "person_wearing_helmet",
        "title": "Personnel inside workshop wear hard hats / safety helmets",
        "type": "colocation",
        "severity": "high",
        "sam_prompts": [
          "person",
          "safety helmet",
          "hard hat"
        ],
        "params": {
          "container_prompt": "person",
          "item_prompt": "safety helmet",
          "min_overlap": 0.25
        },
        "fix_text": "Ensure helmets are worn at all designated workshop entry points and provide helmets for all active personnel."
      },
      {
        "id": "person_wearing_safety_gloves",
        "title": "Personnel handling equipment wear protective safety gloves",
        "type": "colocation",
        "severity": "medium",
        "sam_prompts": [
          "person",
          "safety gloves",
          "protective gloves"
        ],
        "params": {
          "container_prompt": "person",
          "item_prompt": "safety gloves",
          "min_overlap": 0.15
        },
        "fix_text": "Provide cut-resistant safety gloves and enforce mandatory use during active machinery and material handling."
      },
      {
        "id": "floor_free_of_clutter",
        "title": "Workshop walkways and work bays are free of loose floor clutter",
        "type": "absence",
        "severity": "medium",
        "sam_prompts": [
          "loose tools",
          "scrap metal",
          "wooden debris",
          "discarded materials"
        ],
        "params": {
          "threshold": 0.6
        },
        "fix_text": "Clean workshop floor, implement daily 5S housekeeping routines, and store loose materials in designated bins."
      },
      {
        "id": "first_aid_box_visible",
        "title": "First aid kit or station is accessible and clearly marked",
        "type": "presence",
        "severity": "high",
        "sam_prompts": [
          "first aid kit",
          "first aid box",
          "medical cross box"
        ],
        "params": {
          "min_score": 0.6
        },
        "fix_text": "Install a fully stocked, wall-mounted first aid kit in a central, visible location with clear signage."
      },
      {
        "id": "no_loose_cables_walkway",
        "title": "No loose or unbridged power cords across walkways",
        "type": "absence",
        "severity": "high",
        "sam_prompts": [
          "loose cable",
          "extension cord",
          "exposed wire"
        ],
        "params": {
          "threshold": 0.6
        },
        "fix_text": "Reroute power cables overhead or install heavy-duty floor cable bridge protectors across walkway crossings."
      }
    ]
  }
];
