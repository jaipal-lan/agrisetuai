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
