"""Ready-made service-area presets.

A one-click coverage set for the Hyderabad metro (Telangana). Centroid lat/lng
let the distance service compute routes and decide whether a buyer's GPS point is
inside the delivery footprint. Used by the seed (fresh DBs) and the superadmin
"Service areas" one-click button (existing/live DBs).
"""

# (state_name, state_code, district, mandal, latitude, longitude)
HYDERABAD_METRO = [
    ("Telangana", "TG", "Hyderabad", "Kukatpally", 17.4948, 78.3996),
    ("Telangana", "TG", "Hyderabad", "Secunderabad", 17.4399, 78.4983),
    ("Telangana", "TG", "Hyderabad", "Ameerpet", 17.4374, 78.4487),
    ("Telangana", "TG", "Hyderabad", "Serilingampally", 17.4875, 78.3762),
    ("Telangana", "TG", "Hyderabad", "Charminar", 17.3616, 78.4747),
    ("Telangana", "TG", "Rangareddy", "Rajendranagar", 17.3200, 78.4010),
    ("Telangana", "TG", "Rangareddy", "Shamshabad", 17.2403, 78.4294),
    ("Telangana", "TG", "Rangareddy", "L B Nagar", 17.3410, 78.5500),
    ("Telangana", "TG", "Medchal-Malkajgiri", "Medchal", 17.6300, 78.4800),
    ("Telangana", "TG", "Medchal-Malkajgiri", "Malkajgiri", 17.4480, 78.5270),
    ("Telangana", "TG", "Medchal-Malkajgiri", "Uppal", 17.4050, 78.5590),
]

# The wider Telangana + Andhra Pradesh coverage menu. These are LOADED but kept
# NON-serviceable until the superadmin activates a region (once agents/transport
# are onboarded there). Same (state, code, district, mandal, lat, lng) shape.
AP_TG_REGIONS = [
    # --- Telangana ---
    ("Telangana", "TG", "Rangareddy", "Ibrahimpatnam", 17.2400, 78.6600),
    ("Telangana", "TG", "Sangareddy", "Sangareddy", 17.6200, 78.0800),
    ("Telangana", "TG", "Sangareddy", "Patancheru", 17.5300, 78.2600),
    ("Telangana", "TG", "Siddipet", "Siddipet", 18.1000, 78.8500),
    ("Telangana", "TG", "Nalgonda", "Nalgonda", 17.0500, 79.2700),
    ("Telangana", "TG", "Nalgonda", "Miryalaguda", 16.8716, 79.5650),
    ("Telangana", "TG", "Warangal", "Warangal", 17.9700, 79.5900),
    ("Telangana", "TG", "Warangal", "Hanamkonda", 18.0100, 79.5600),
    ("Telangana", "TG", "Khammam", "Khammam", 17.2500, 80.1500),
    ("Telangana", "TG", "Khammam", "Kothagudem", 17.5500, 80.6200),
    ("Telangana", "TG", "Karimnagar", "Karimnagar", 18.4400, 79.1300),
    ("Telangana", "TG", "Nizamabad", "Nizamabad", 18.6700, 78.0900),
    ("Telangana", "TG", "Mahbubnagar", "Mahbubnagar", 16.7400, 78.0000),
    ("Telangana", "TG", "Mahbubnagar", "Shadnagar", 17.0700, 78.2000),
    ("Telangana", "TG", "Adilabad", "Adilabad", 19.6700, 78.5300),
    # --- Andhra Pradesh ---
    ("Andhra Pradesh", "AP", "Guntur", "Guntur", 16.3100, 80.4400),
    ("Andhra Pradesh", "AP", "Guntur", "Tenali", 16.2430, 80.6400),
    ("Andhra Pradesh", "AP", "Krishna", "Vijayawada", 16.5100, 80.6500),
    ("Andhra Pradesh", "AP", "Krishna", "Machilipatnam", 16.1900, 81.1400),
    ("Andhra Pradesh", "AP", "Prakasam", "Ongole", 15.5000, 80.0500),
    ("Andhra Pradesh", "AP", "Nellore", "Nellore", 14.4400, 79.9900),
    ("Andhra Pradesh", "AP", "Chittoor", "Tirupati", 13.6300, 79.4200),
    ("Andhra Pradesh", "AP", "Chittoor", "Chittoor", 13.2200, 79.1000),
    ("Andhra Pradesh", "AP", "Kurnool", "Kurnool", 15.8300, 78.0400),
    ("Andhra Pradesh", "AP", "Anantapur", "Anantapur", 14.6800, 77.6000),
    ("Andhra Pradesh", "AP", "Kadapa", "Kadapa", 14.4700, 78.8200),
    ("Andhra Pradesh", "AP", "East Godavari", "Kakinada", 16.9600, 82.2400),
    ("Andhra Pradesh", "AP", "East Godavari", "Rajahmundry", 17.0000, 81.8000),
    ("Andhra Pradesh", "AP", "West Godavari", "Eluru", 16.7100, 81.1000),
    ("Andhra Pradesh", "AP", "West Godavari", "Bhimavaram", 16.5400, 81.5200),
    ("Andhra Pradesh", "AP", "Visakhapatnam", "Visakhapatnam", 17.6900, 83.2200),
    ("Andhra Pradesh", "AP", "Vizianagaram", "Vizianagaram", 18.1100, 83.4100),
    ("Andhra Pradesh", "AP", "Srikakulam", "Srikakulam", 18.3000, 83.9000),
]
