#!/usr/bin/env python3
"""
Generate synthetic Indian Mutual Fund stress testing dataset with 25+ realistic investor profiles,
fund portfolio asset compositions, and stress outflow event scenarios.
"""

import json
import random
from pathlib import Path

# Indian Seed Data
FIRST_NAMES = [
    "Aarav", "Aditi", "Adhish", "Ananya", "Dev", "Diya", "Ishaan", "Kavya",
    "Manish", "Neha", "Pranav", "Pooja", "Rahul", "Rhea", "Rohan", "Siddharth",
    "Sneha", "Tanvi", "Varun", "Vikram", "Zoya", "Arjun", "Kunal", "Meera", "Suresh"
]

LAST_NAMES = [
    "Agarwal", "Bose", "Choudhury", "Das", "Deshmukh", "Gupta", "Iyer", "Jain",
    "Kapoor", "Kulkarni", "Mehta", "Nair", "Patel", "Reddy", "Sharma", "Singh",
    "Thite", "Trivedi", "Varma", "Venkatesh"
]

SCHEME_CATEGORIES = [
    {"name": "Credit Risk Fund", "code": "credit_risk", "prc": "B-III", "aum_cr": 2500},
    {"name": "Medium Duration Fund", "code": "medium_duration", "prc": "B-II", "aum_cr": 4200},
    {"name": "Dynamic Bond Fund", "code": "dynamic_bond", "prc": "A-III", "aum_cr": 6800},
    {"name": "Corporate Bond Fund", "code": "corporate_bond", "prc": "A-II", "aum_cr": 12500},
    {"name": "Banking & PSU Debt Fund", "code": "banking_psu", "prc": "A-I", "aum_cr": 8900},
    {"name": "Liquid Fund (Exempt)", "code": "liquid", "prc": "A-I", "aum_cr": 18000},
    {"name": "Overnight Fund (Exempt)", "code": "overnight", "prc": "A-I", "aum_cr": 15000}
]

def generate_pan():
    letters = "ABCDE"
    mid_letter = random.choice(["P", "C", "H", "F", "A", "T"])
    last_name_init = random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    digits = f"{random.randint(1000, 9999)}"
    end_char = random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    return f"ABC{mid_letter}{last_name_init}{digits}{end_char}"

def generate_aadhaar():
    return "".join([str(random.randint(0, 9)) for _ in range(12)])

def generate_dataset():
    investors = []
    for i in range(30):
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        full_name = f"{first} {last}"
        pan = generate_pan()
        aadhaar = generate_aadhaar()
        
        # Decide category: Retail (<= 2L) or HNI/Institutional (> 2L)
        is_retail = random.random() < 0.4
        if is_retail:
            amount_inr = round(random.uniform(25_000, 195_000), 2)
        else:
            amount_inr = round(random.uniform(500_000, 50_000_000), 2)
            
        investors.append({
            "investor_id": f"INV-{1000 + i}",
            "investor_name": full_name,
            "investor_pan": pan,
            "investor_aadhaar": aadhaar,
            "is_retail": is_retail,
            "simulated_amount_inr": amount_inr,
            "transaction_type": "redemption" if random.random() < 0.85 else "subscription",
            "preferred_category": random.choice(SCHEME_CATEGORIES)["code"]
        })
        
    dataset = {
        "schemes": SCHEME_CATEGORIES,
        "investors": investors,
        "market_stress_scenarios": [
            {
                "scenario_id": "SCEN-01-DISLOCATION-CRISIS",
                "title": "Severe Market Dislocation & Secondary Market Illiquidity",
                "description": "SEBI declares market dislocation following sovereign yield spike. 18% cumulative redemption wave.",
                "dislocation_active": True,
                "net_outflow_pct": 18.5,
                "target_scheme": "credit_risk"
            },
            {
                "scenario_id": "SCEN-02-NORMAL-STRESS-SPIKE",
                "title": "Quarter-End Corporate Advance Tax Outflow",
                "description": "Normal market conditions, but corporate redemption reaches 6.8% breaching 5% discretionary threshold.",
                "dislocation_active": False,
                "net_outflow_pct": 6.8,
                "target_scheme": "medium_duration"
            },
            {
                "scenario_id": "SCEN-03-RETAIL-EXEMPT-TRANSACTION",
                "title": "Retail Investor ₹1.5L Redemption",
                "description": "Retail transaction under ₹2 Lakh threshold; exempt from swing pricing even during stress.",
                "dislocation_active": True,
                "net_outflow_pct": 12.0,
                "target_scheme": "dynamic_bond"
            },
            {
                "scenario_id": "SCEN-04-EXEMPT-LIQUID-FUND",
                "title": "Large Institutional Redemption in Liquid Fund",
                "description": "Liquid and Overnight schemes are statutorily exempt from swing pricing framework.",
                "dislocation_active": True,
                "net_outflow_pct": 15.0,
                "target_scheme": "liquid"
            }
        ]
    }
    
    out_path = Path(__file__).resolve().parent.parent / "backend" / "seed_data.json"
    with open(out_path, "w") as f:
        json.dump(dataset, f, indent=2)
    print(f"Generated synthetic dataset with {len(investors)} investors and saved to {out_path}")

if __name__ == "__main__":
    generate_dataset()
