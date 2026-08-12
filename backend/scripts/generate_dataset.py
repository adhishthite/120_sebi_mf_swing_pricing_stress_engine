import json
import random
import sys
from pathlib import Path

# Add backend directory to Python path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from services.agents import Orchestrator


def generate_synthetic_dataset(num_records: int = 50) -> list:
    risk_options = ["LOW", "MODERATE", "HIGH", "VERY_HIGH"]
    prc_options = [
        "A-I",
        "A-II",
        "A-III",
        "B-I",
        "B-II",
        "B-III",
        "C-I",
        "C-II",
        "C-III",
    ]

    first_names = [
        "Ramesh",
        "Suresh",
        "Priya",
        "Ananya",
        "Amit",
        "Rahul",
        "Neha",
        "Vikram",
        "Sneha",
        "Karan",
    ]
    last_names = [
        "Sharma",
        "Verma",
        "Patel",
        "Gupta",
        "Mehta",
        "Singh",
        "Joshi",
        "Rao",
        "Nair",
        "Reddy",
    ]

    dataset = []

    for i in range(num_records):
        # Generate random asset ratios summing to 1.0
        r1 = random.uniform(0.1, 0.7)
        r2 = random.uniform(0.1, 1.0 - r1 - 0.05)
        r3 = 1.0 - r1 - r2

        # Random risk metrics
        risk = random.choice(risk_options)
        prc = random.choice(prc_options)

        # Outflow: standard redemptions range from 0.1% to 25.0%
        outflow_pct = round(random.uniform(0.1, 25.0), 2)

        # AUM: from 100 Million INR to 50 Billion INR
        aum = round(random.uniform(1e8, 5e10), 2)

        # 20% chance of leaked PII
        leak_pii = random.random() < 0.20
        if leak_pii:
            name = f"{random.choice(first_names)} {random.choice(last_names)}"
            pan = (
                "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=5))
                + "".join(random.choices("0123456789", k=4))
                + random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
            )
            aadhaar = "".join(random.choices("0123456789", k=12))
        else:
            name = f"***MASKED_INVESTOR_{random.randint(100, 999)}***"
            pan = f"XXXXX{random.randint(1000, 9999)}F"
            aadhaar = f"XXXX-XXXX-{random.randint(1000, 9999)}"

        record = {
            "scenario_id": f"SCENARIO_{i + 1:03d}",
            "aum": aum,
            "initial_nav": round(random.uniform(10.0, 250.0), 4),
            "net_outflow_pct": outflow_pct,
            "risk_o_meter": risk,
            "prc_cell": prc,
            "portfolio_exposure": {
                "liquid_ratio": round(r1, 4),
                "semi_liquid_ratio": round(r2, 4),
                "illiquid_ratio": round(r3, 4),
            },
            "investor_name": name,
            "investor_pan": pan,
            "investor_aadhaar": aadhaar,
        }
        dataset.append(record)

    return dataset


if __name__ == "__main__":
    output_dir = Path(__file__).resolve().parent.parent
    output_file = output_dir / "synthetic_stress_dataset.json"

    print(f"Generating {100} synthetic stress records...")
    records = generate_synthetic_dataset(100)

    with open(output_file, "w") as f:
        json.dump(records, f, indent=2)

    print(f"Successfully generated and wrote dataset to: {output_file}")

    # Run one simulation to check
    sample_res = Orchestrator.run_simulation(records[0])
    print(f"Sample simulation successful. Optimal Strategy chosen: {sample_res['optimal_strategy']}")
