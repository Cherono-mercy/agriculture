import frappe
from frappe.utils import getdate

def execute(filters=None):
    columns = get_columns()
    data = get_data()
    return columns, data

def get_columns():
    week_cols = [{"label": f"W{w}", "fieldname": f"week_{w}", "fieldtype": "Float", "width": 80} for w in range(1, 53)]
    return [
        {"label": "Variety", "fieldname": "variety", "fieldtype": "Link", "options": "Item", "width": 150},
        {"label": "Greenhouse", "fieldname": "greenhouse", "fieldtype": "Data", "width": 120},
    ] + week_cols + [
        {"label": "Annual Total", "fieldname": "total", "fieldtype": "Float", "width": 120},
    ]

def get_data():
    # Get correction percentages from settings
    settings = frappe.get_single("Agriculture Settings")
    corrections = settings.get("weekly_corrections") or {}  # e.g., {1: 100, 2: 95, ..., 52: 105}

    data = []
    crop_cycles = frappe.get_all("Crop Cycle", fields=["name", "greenhouse", "variety", "area", "yield_per_m2"])

    for cycle in crop_cycles:
        variety = cycle.variety
        greenhouse = cycle.greenhouse
        area = cycle.area or 0
        yield_per_m2 = cycle.yield_per_m2

        # fallback to Item default
        if not yield_per_m2:
            yield_per_m2 = frappe.db.get_value("Item", variety, "default_yield") or 0

        base_weekly = (yield_per_m2 * area) / 52
        row = {
            "variety": variety,
            "greenhouse": greenhouse,
        }

        total = 0
        for w in range(1, 53):
            correction = corrections.get(str(w), 100)  # default 100%
            corrected = round(base_weekly * (correction / 100), 2)
            row[f"week_{w}"] = corrected
            total += corrected

        row["total"] = round(total, 2)
        data.append(row)

    return data
