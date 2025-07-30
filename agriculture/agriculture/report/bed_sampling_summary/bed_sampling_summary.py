# Copyright (c) 2025, Your Name and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import getdate, add_days

def execute(filters=None):
    conditions = []
    if filters.get("greenhouse"):
        conditions.append("bs.greenhouse = %(greenhouse)s")
    if filters.get("variety"):
        conditions.append("bs.variety = %(variety)s")
    if filters.get("week_no"):
        conditions.append("bs.week_no = %(week_no)s")

    condition_sql = " AND ".join(conditions)
    if condition_sql:
        condition_sql = " AND " + condition_sql

    data = frappe.db.sql("""
        SELECT
            bs.name AS "ID",
            bs.greenhouse AS "Greenhouse",
            bs.variety AS "Variety",
            bs.week_no AS "Week No.",
            bs.sampling_area AS "Sampling Area",
            bs.total_variety_area AS "Total Variety Area",
            bs.date AS "Sampling Date"
        FROM `tabBed Sampling Form` bs
        WHERE bs.docstatus = 1 {conditions}
        ORDER BY bs.date DESC
    """.format(conditions=condition_sql), filters, as_dict=1)

    columns = [
        {"label": "ID", "fieldname": "ID", "fieldtype": "Link", "options": "Bed Sampling Form", "width": 120},
        {"label": "Greenhouse", "fieldname": "Greenhouse", "fieldtype": "Link", "options": "Warehouse", "width": 120},
        {"label": "Variety", "fieldname": "Variety", "fieldtype": "Link", "options": "Item", "width": 120},
        {"label": "Week No.", "fieldname": "Week No.", "fieldtype": "Int", "width": 80},
        {"label": "Sampling Area", "fieldname": "Sampling Area", "fieldtype": "Float", "width": 100},
        {"label": "Total Variety Area", "fieldname": "Total Variety Area", "fieldtype": "Float", "width": 120},
        {"label": "Sampling Date", "fieldname": "Sampling Date", "fieldtype": "Date", "width": 100},
    ]

    return columns, data


@frappe.whitelist()
def generate_forecasting_form(greenhouse, variety, week_no):
    sampling_week = int(week_no)

    # ✅ 1️⃣ Fetch dynamic growth stages config
    agri_settings = frappe.get_doc("Agriculture Settings")
    growth_stage_days = {
        row.growth_stage: row.days_to_harvest for row in agri_settings.growth_stages
    }

    # fallback in case no config
    if not growth_stage_days:
        frappe.throw("No growth stages configured in Agriculture Settings. Please add them first.")

    samplings = frappe.get_all(
        "Bed Sampling Form",
        filters={
            "greenhouse": greenhouse,
            "variety": variety,
            "week_no": sampling_week
        },
        fields=["name", "date", "sampling_area", "total_variety_area"]
    )

    if not samplings:
        frappe.throw("No sampling found for selected greenhouse, variety and week.")

    growth_stage_totals = {}
    sampling_area_total = 0
    total_variety_area_total = 0

    for s in samplings:
        doc = frappe.get_doc("Bed Sampling Form", s.name)
        for row in doc.growth_stages:
            growth_stage_totals.setdefault(row.growth_stage, []).append(row.number)

        sampling_area_total += doc.sampling_area or 0
        total_variety_area_total += doc.total_variety_area or 0

    count = len(samplings)
    avg_sampling_area = sampling_area_total / count if count else 1
    avg_total_area = total_variety_area_total / count if count else 1

    sampling_date = getdate(samplings[0].date)

    weekly_totals = {}

    # ✅ 2️⃣ Use dynamic config
    for stage, numbers in growth_stage_totals.items():
        avg_count = sum(numbers) / len(numbers)
        scaled_count = avg_count * (avg_total_area / avg_sampling_area)

        days = growth_stage_days.get(stage)
        if days:
            harvest_date = add_days(sampling_date, days)
            iso_week = harvest_date.isocalendar()[1]
            offset = (iso_week - sampling_week + 1) if iso_week >= sampling_week else (iso_week + 52 - sampling_week + 1)
            if 1 <= offset <= 10:
                weekly_totals[offset] = weekly_totals.get(offset, 0) + scaled_count

    last_week = sampling_week - 1 if sampling_week > 1 else 52

    last_week_harvest = frappe.db.sql("""
        SELECT SUM(sed.qty)
        FROM `tabStock Entry` se
        JOIN `tabStock Entry Detail` sed ON sed.parent = se.name
        WHERE sed.item_code = %s
          AND sed.t_warehouse = %s
          AND WEEK(se.posting_date, 1) = %s
          AND se.docstatus = 1
    """, (variety, greenhouse, last_week))[0][0] or 0

    prev = frappe.get_all(
        "Forecasting Form",
        filters={"greenhouse": greenhouse, "variety": variety, "week_no": last_week},
        fields=["name"]
    )

    last_week_forecast = 0
    if prev:
        last_doc = frappe.get_doc("Forecasting Form", prev[0].name)
        for r in last_doc.forecast_details:
            if r.week_no == 1:
                last_week_forecast = r.current_forecast or 0
                break

    forecast = frappe.get_doc({
        "doctype": "Forecasting Form",
        "greenhouse": greenhouse,
        "variety": variety,
        "sampling_date": sampling_date,
        "week_no": sampling_week,
        "custom_week_no": sampling_week 
    })

    for i in range(10):
        offset = i + 1
        iso_week = (sampling_week + i - 1) % 52 + 1
        expected = weekly_totals.get(offset) or 0

        forecast.append("forecast_details", {
            "week_no": iso_week,
            "expected_production": expected,
            "last_week_harvest": last_week_harvest if offset == 1 else 0,
            "last_week_forecast": last_week_forecast if offset == 1 else 0,
            "current_forecast": None
        })

    forecast.insert(ignore_permissions=True)
    return forecast.name


# ✅ NEW: Server-side helper method to calculate sampling_area and total_variety_area
# @frappe.whitelist()
# def get_sampling_defaults(greenhouse, variety, sample_bed_length=4):
#     sample_bed_length = float(sample_bed_length or 4)

#     crop = frappe.get_all(
#         "Crop Cycle",
#         filters={"greenhouse": greenhouse, "variety": variety},
#         fields=["bed_width", "area"]
#     )

#     if not crop:
#         frappe.throw("No Crop Cycle found for selected Greenhouse and Variety.")

#     bed_width = crop[0].bed_width or 0
#     total_area = crop[0].area or 0
#     sampling_area = bed_width * sample_bed_length

#     return {
#         "sampling_area": sampling_area,
#         "total_variety_area": total_area
#     }
