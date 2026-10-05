"""v6 detector class list and per-source label mappings -- the single place
every v6 converter reads them from (see datasets/v6/SOURCES.md for why each
source was chosen).

IDs 0-8 keep the nh5_v5 numbering so app.py / 9_plate_pipeline.py keep working.
"""

CLASSES = [
    "person",          # 0
    "bicycle",         # 1
    "car",             # 2
    "motorcycle",      # 3
    "bus",             # 4
    "truck",           # 5
    "pothole",         # 6
    "license_plate",   # 7
    "auto",            # 8
    "damaged_vehicle", # 9
    "traffic_cone",    # 10
    "barricade",       # 11
    "zebra_crossing",  # 12
]
CLASS_IDS = {name: i for i, name in enumerate(CLASSES)}

# source label -> v6 class name, or None to drop the box
UVH26_MAP = {
    "Hatchback": "car",
    "Sedan": "car",
    "SUV": "car",
    "MUV": "car",
    "Van": "car",
    "Bus": "bus",
    "Mini-bus": "bus",
    "Tempo-traveller": "bus",
    "Truck": "truck",
    "LCV": "truck",
    "Three-wheeler": "auto",
    "Two-wheeler": "motorcycle",
    "Bicycle": "bicycle",
    "Others": None,
}

CDSET_MAP = {
    0: "zebra_crossing",  # crosswalk
    1: None,              # guide_arrows
}

# source class id -> v6 class name; ids not listed are dropped
PLATE_MAP = {0: "license_plate"}
DASHCAM_MAP = {0: "barricade", 1: "pothole"}  # Dashcam POV Potholes & Barricades (classes.txt order)

# User-supplied Roboflow accident exports (datasets/car accidents/*.zip): class 0 is the crash box in all
# three (hackcimat 'accident', ai-challenge '-', car-accidents 'Colision'); class 1 'fire' is dropped --
# most fire boxes are wildfires and burning buildings, not road incidents
ACCIDENT_MAP = {0: "damaged_vehicle"}

# Kaggle cubeai/traffic-accident-detection-for-yolov8 (Roboflow export, Chinese class names):
# 0 自行车 bicycle, 1 自行车撞自行车 bicycle hits bicycle, 2 自行车撞物 bicycle hits object, 3 自行车撞人 bicycle hits
# person, 4 小汽车 car, 5 小汽车撞自行车 car hits bicycle, 6 小汽车撞小汽车 car hits car, 7 小汽车撞物 car hits object,
# 8 小汽车撞人 car hits person, 9 人 person
CUBEAI_MAP = {0: "bicycle", 1: "damaged_vehicle", 2: "damaged_vehicle", 3: "damaged_vehicle", 4: "car",
              5: "damaged_vehicle", 6: "damaged_vehicle", 7: "damaged_vehicle", 8: "damaged_vehicle", 9: "person"}
CUBEAI_CRASH_TYPES = {1: "bicycle", 2: "bicycle", 3: "bicycle", 5: "car", 6: "car", 7: "car", 8: "car"}

# Kaggle pampanadeepakbabu/road-accident-anamoly-dataset: bike, car, person, truck, bike_accident,
# car_accident, road_damage, speed_bump, unsurfaced_road. road_damage covers cracks and worn tarmac as
# well as holes, so it isn't taken as pothole; speed bumps and unsurfaced road aren't v6 classes.
PAMPANA_MAP = {0: "motorcycle", 1: "car", 2: "person", 3: "truck", 4: "damaged_vehicle", 5: "damaged_vehicle",
               6: None, 7: None, 8: None}
PAMPANA_CRASH_TYPES = {4: "motorcycle", 5: "car"}

# Exports whose own classes state how bad the crash is -> categories/06_road_accidents/{moderate,severe,fire}.
# hackcimat and ai-challenge label fire separately: an image with a crash box AND a fire box is a vehicle
# fire (fire-only images are wildfires and burning buildings and are dropped at conversion).
ACCIDENT_SEVERITY_BY_CLASS = {
    "accidents_amedeograndi": {0: "moderate", 1: "severe"},
    "accidents_hackcimat": {1: "fire"},
    "accidents_ai_challenge": {1: "fire"},
}

# Any other Roboflow accident export dropped in datasets/car accidents/: its class NAME decides the v6
# class. Rules are checked in order and the first whose word appears in the lower-cased name wins, so
# "non-accident" is dropped before "accident" can match. Names matching no rule are dropped too.
ACCIDENT_CLASS_RULES = [
    (("non", "no-", "no_", "not ", "normal", "fire", "smoke", "flame"), None),
    (("accident", "crash", "collision", "colision", "damage", "wreck"), "damaged_vehicle"),
]
# vehicle type named in an accident class or file name; first match wins, so "motor" is checked before
# "car", "bicycle" before anything with "cycle", "autorickshaw" before "car"
ACCIDENT_VEHICLE_HINTS = [("bicycle", "bicycle"), ("motor", "motorcycle"), ("mt-acc", "motorcycle"), ("bike", "motorcycle"),
                          ("bus", "bus"), ("truck", "truck"), ("lorry", "truck"), ("rickshaw", "auto"),
                          ("three_wheel", "auto"), ("three-wheel", "auto"), ("tuk", "auto"), ("car", "car")]

# Raqabah severity folder name -> short name (image-level labels, no boxes; all scenes are cars)
RAQABAH_SEVERITY = {
    "Minior": "minor",
    "Moderate": "moderate",
    "Severe/Car_Flipped": "severe_car_flipped",
    "Severe/Car_Fire": "severe_car_fire",
}

# Open Images V7 boxable class name -> v6 class name (Man/Woman/Boy/Girl are boxed instead of Person)
OPEN_IMAGES_MAP = {
    "Person": "person",
    "Man": "person",
    "Woman": "person",
    "Boy": "person",
    "Girl": "person",
    "Bicycle": "bicycle",
    "Car": "car",
    "Taxi": "car",
    "Van": "car",
    "Motorcycle": "motorcycle",
    "Bus": "bus",
    "Truck": "truck",
    "Vehicle registration plate": "license_plate",
}

# Road users nh5_v5 can propose when pre-labeling classes a source doesn't annotate.
PRELABEL_CLASSES = ["person", "bicycle", "car", "motorcycle", "bus", "truck", "auto"]

# Classes each source labels exhaustively in every image -- pre-labeling never proposes these.
# Anything missing here (e.g. Open Images, whose vehicle boxes aren't exhaustive) gets proposals for every
# PRELABEL_CLASSES entry, de-duplicated against the boxes the source already has.
FULLY_LABELED = {
    "uvh26": {"bicycle", "car", "motorcycle", "bus", "truck", "auto"},
}
