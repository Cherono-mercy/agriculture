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

    # ✅ Get growth stage config for this variety from the Item doctype
    item = frappe.get_doc("Item", variety)
    growth_stage_days = {
        row.growth_stage: row.days_to_harvest for row in item.custom_variety_growth_stages
    }

    if not growth_stage_days:
        frappe.throw("No growth stages configured for this variety in the Item master.")

    # ✅ Get all sampling forms for the week/greenhouse/variety
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
            growth_stage_totals.setdefault(row.growth_stage, []).append(row.number or 0)

        sampling_area_total += doc.sampling_area or 0
        total_variety_area_total += doc.total_variety_area or 0

    count = len(samplings)
    avg_sampling_area = sampling_area_total / count if count else 1
    avg_total_area = total_variety_area_total / count if count else 1

    sampling_date = getdate(samplings[0].date)

    weekly_totals = {}

    # ✅ Calculate weekly totals per stage
    for stage, numbers in growth_stage_totals.items():
        avg_count = sum(numbers) / len(numbers)
        scaled_count = avg_count * (avg_total_area / avg_sampling_area)

        days = growth_stage_days.get(stage)
        if days is not None:
            harvest_date = add_days(sampling_date, days)
            iso_week = harvest_date.isocalendar()[1]

            offset = (iso_week - sampling_week + 1) if iso_week >= sampling_week else (iso_week + 52 - sampling_week + 1)
            if 1 <= offset <= 10:
                weekly_totals[offset] = weekly_totals.get(offset, 0) + scaled_count

    # ✅ Get last week's harvest
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

    # ✅ Get previous week's forecast
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

    # ✅ Create Forecasting Form
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
