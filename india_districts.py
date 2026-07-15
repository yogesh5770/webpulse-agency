"""District-level geography for lead discovery.

DISTRICTS is an ordered list of (state, district) pairs covering all Indian
states and union territories. Tamil Nadu is placed FIRST (home market) so the
worker fully covers it before moving outward across the country.

The 24/7 worker walks this list one district at a time (see lead_queries.py),
combining each district with a business niche, so discovery systematically
sweeps every district in every state instead of re-scanning a few big cities.
"""

# --- Tamil Nadu FIRST: all 38 districts (home market -> cover it fully) ---
_TAMIL_NADU = [
    "Chennai", "Coimbatore", "Cuddalore", "Dharmapuri", "Dindigul", "Erode",
    "Kallakurichi", "Kanchipuram", "Kanyakumari", "Karur", "Krishnagiri",
    "Madurai", "Mayiladuthurai", "Nagapattinam", "Namakkal", "Nilgiris",
    "Perambalur", "Pudukkottai", "Ramanathapuram", "Ranipet", "Salem",
    "Sivaganga", "Tenkasi", "Thanjavur", "Theni", "Thoothukudi",
    "Tiruchirappalli", "Tirunelveli", "Tirupathur", "Tiruppur", "Tiruvallur",
    "Tiruvannamalai", "Tiruvarur", "Vellore", "Viluppuram", "Virudhunagar",
    "Ariyalur", "Chengalpattu",
]

# --- Rest of India: state -> districts (representative/major districts).
# Kept broad and practical; expands nationwide after Tamil Nadu.
_STATES = {
    "Andhra Pradesh": [
        "Anantapur", "Chittoor", "East Godavari", "Guntur", "Krishna",
        "Kurnool", "Nellore", "Prakasam", "Srikakulam", "Visakhapatnam",
        "Vizianagaram", "West Godavari", "Kadapa",
    ],
    "Arunachal Pradesh": [
        "Itanagar", "Tawang", "Papum Pare", "West Kameng", "Lohit",
        "Changlang", "Tirap",
    ],
    "Assam": [
        "Kamrup", "Guwahati", "Dibrugarh", "Cachar", "Nagaon", "Sonitpur",
        "Barpeta", "Jorhat", "Tinsukia", "Dhubri", "Sivasagar",
    ],
    "Bihar": [
        "Patna", "Gaya", "Bhagalpur", "Muzaffarpur", "Purnia", "Darbhanga",
        "Begusarai", "Nalanda", "Rohtas", "Saran", "Vaishali", "East Champaran",
    ],
    "Chhattisgarh": [
        "Raipur", "Bilaspur", "Durg", "Korba", "Raigarh", "Rajnandgaon",
        "Bastar", "Surguja",
    ],
    "Goa": ["North Goa", "South Goa"],
    "Gujarat": [
        "Ahmedabad", "Surat", "Vadodara", "Rajkot", "Bhavnagar", "Jamnagar",
        "Junagadh", "Gandhinagar", "Anand", "Kutch", "Mehsana", "Navsari",
    ],
    "Haryana": [
        "Faridabad", "Gurugram", "Panipat", "Ambala", "Hisar", "Karnal",
        "Rohtak", "Sonipat", "Yamunanagar", "Panchkula",
    ],
    "Himachal Pradesh": [
        "Shimla", "Kangra", "Mandi", "Solan", "Hamirpur", "Una", "Kullu",
        "Bilaspur",
    ],
    "Jharkhand": [
        "Ranchi", "Dhanbad", "Jamshedpur", "Bokaro", "Hazaribagh", "Deoghar",
        "Giridih", "Dumka",
    ],
    "Karnataka": [
        "Bengaluru Urban", "Mysuru", "Mangaluru", "Hubli-Dharwad", "Belagavi",
        "Kalaburagi", "Ballari", "Vijayapura", "Shivamogga", "Tumakuru",
        "Davanagere", "Udupi", "Hassan",
    ],
    "Kerala": [
        "Thiruvananthapuram", "Kollam", "Pathanamthitta", "Alappuzha",
        "Kottayam", "Idukki", "Ernakulam", "Thrissur", "Palakkad",
        "Malappuram", "Kozhikode", "Wayanad", "Kannur", "Kasaragod",
    ],
    "Madhya Pradesh": [
        "Indore", "Bhopal", "Jabalpur", "Gwalior", "Ujjain", "Sagar", "Rewa",
        "Satna", "Ratlam", "Dewas",
    ],
    "Maharashtra": [
        "Mumbai City", "Mumbai Suburban", "Pune", "Nagpur", "Nashik", "Thane",
        "Aurangabad", "Solapur", "Kolhapur", "Amravati", "Nanded", "Sangli",
        "Jalgaon", "Ahmednagar", "Satara",
    ],
    "Manipur": ["Imphal West", "Imphal East", "Thoubal", "Bishnupur"],
    "Meghalaya": ["East Khasi Hills", "West Garo Hills", "Ri Bhoi", "Jaintia Hills"],
    "Mizoram": ["Aizawl", "Lunglei", "Champhai"],
    "Nagaland": ["Kohima", "Dimapur", "Mokokchung", "Tuensang"],
    "Odisha": [
        "Khordha", "Cuttack", "Ganjam", "Sundargarh", "Balasore", "Sambalpur",
        "Puri", "Mayurbhanj", "Bhubaneswar",
    ],
    "Punjab": [
        "Ludhiana", "Amritsar", "Jalandhar", "Patiala", "Bathinda", "Mohali",
        "Hoshiarpur", "Pathankot", "Moga",
    ],
    "Rajasthan": [
        "Jaipur", "Jodhpur", "Udaipur", "Kota", "Bikaner", "Ajmer", "Bhilwara",
        "Alwar", "Sikar", "Sri Ganganagar",
    ],
    "Sikkim": ["East Sikkim", "South Sikkim", "West Sikkim"],
    "Telangana": [
        "Hyderabad", "Rangareddy", "Warangal", "Karimnagar", "Khammam",
        "Nizamabad", "Nalgonda", "Medak",
    ],
    "Tripura": ["West Tripura", "Gomati", "North Tripura", "Dhalai"],
    "Uttar Pradesh": [
        "Lucknow", "Kanpur Nagar", "Ghaziabad", "Agra", "Varanasi", "Meerut",
        "Prayagraj", "Bareilly", "Aligarh", "Moradabad", "Gorakhpur",
        "Noida", "Saharanpur", "Jhansi",
    ],
    "Uttarakhand": [
        "Dehradun", "Haridwar", "Nainital", "Udham Singh Nagar", "Pauri Garhwal",
    ],
    "West Bengal": [
        "Kolkata", "North 24 Parganas", "South 24 Parganas", "Howrah",
        "Hooghly", "Bardhaman", "Nadia", "Murshidabad", "Darjeeling",
        "Malda", "Jalpaiguri",
    ],
    # --- Union Territories ---
    "Delhi": [
        "New Delhi", "North Delhi", "South Delhi", "East Delhi", "West Delhi",
        "Central Delhi",
    ],
    "Jammu and Kashmir": ["Srinagar", "Jammu", "Anantnag", "Baramulla", "Udhampur"],
    "Ladakh": ["Leh", "Kargil"],
    "Puducherry": ["Puducherry", "Karaikal", "Mahe", "Yanam"],
    "Chandigarh": ["Chandigarh"],
    "Andaman and Nicobar Islands": ["South Andaman", "Nicobar", "North and Middle Andaman"],
    "Dadra and Nagar Haveli and Daman and Diu": ["Daman", "Diu", "Silvassa"],
    "Lakshadweep": ["Kavaratti"],
}


def _build() -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = [("Tamil Nadu", d) for d in _TAMIL_NADU]
    for state, districts in _STATES.items():
        for d in districts:
            pairs.append((state, d))
    return pairs


# Ordered (state, district) pairs. Tamil Nadu first, then the rest of India.
DISTRICTS: list[tuple[str, str]] = _build()
