import frappe
from frappe.utils import getdate, add_days

@frappe.whitelist()
def generate_forecasting_form(greenhouse, variety, week_no):
    sampling_week = int(week_no)

    # ✅ Fetch item to get variety_type (item_group) and custom_growth_stage_group
    item = frappe.get_doc("Item", variety)
    variety_type = item.item_group
    custom_growth_stage_group = item.custom_growth_stage_group

    # ✅ Get growth stage configuration from Variety Growth Stages
    filters = {"variety_type": variety_type}
    if custom_growth_stage_group:
        filters["growth_stage_group"] = custom_growth_stage_group

    config = frappe.get_all(
        "Variety Growth Stages",
        filters=filters,
        fields=["name"]
    )

    if not config:
        frappe.throw("No growth stage configuration found for the selected variety type and custom growth stage group.")

    config_name = config[0].name
    config_doc = frappe.get_doc("Variety Growth Stages", config_name)

    # ✅ Map days_to_harvest for each stage
    growth_stage_days = {}
    for row in config_doc.growth_stage_configuration:
        if row.growth_stage and row.days_to_harvest is not None:
            growth_stage_days[row.growth_stage] = row.days_to_harvest

    if not growth_stage_days:
        frappe.throw("Growth stage configuration is empty or invalid.")

    # ✅ Get all sampling forms for the week/greenhouse/variety
    samplings = frappe.get_all(
        "Bed Sampling Form",
        filters={
            "greenhouse": greenhouse,
            "variety": variety,
            "week_no": sampling_week
        },
        fields=["name", "date", "total_variety_area", "sample_bed_length"]
    )

    if not samplings:
        frappe.throw("No sampling found for selected greenhouse, variety and week.")

    # ✅ Fetch bed width from Crop Cycle
    bed_width = frappe.db.get_value("Crop Cycle", {
        "greenhouse": greenhouse,
        "variety": variety
    }, "bed_width") or 1

    # --- UPDATED AGGREGATION LOGIC ---
    growth_stage_totals = {
        "Rice stage": [],
        "Ball stage": [],
        "Colour Break stage": [],
        "Full Colour Break stage": []
    }
    sampling_area_total = 0
    total_variety_area_total = 0

    for s in samplings:
        doc = frappe.get_doc("Bed Sampling Form", s.name)

        for row in doc.growth_stages:
            # ✅ Collect all samples from child table
            growth_stage_totals["Rice stage"].append(row.rice_stage or 0)
            growth_stage_totals["Ball stage"].append(row.ball_stage or 0)
            growth_stage_totals["Colour Break stage"].append(row.colour_break_stage or 0)
            growth_stage_totals["Full Colour Break stage"].append(row.full_colour_break_stage or 0)

        # ✅ Use calculated sampling area: sample_bed_length * bed_width
        calculated_sampling_area = (doc.sample_bed_length or 0) * bed_width
        sampling_area_total += calculated_sampling_area
        total_variety_area_total += doc.total_variety_area or 0

    count = len(samplings)
    avg_sampling_area = sampling_area_total / count if count else 1
    avg_total_area = total_variety_area_total / count if count else 1

    sampling_date = getdate(samplings[0].date)
    weekly_totals = {}

    # ✅ Calculate forecast per growth stage
    for stage, numbers in growth_stage_totals.items():
        if not numbers:
            continue

        avg_count = sum(numbers) / len(numbers)  # average across all samples
        scaled_count = avg_count * (avg_total_area / avg_sampling_area)

        days = growth_stage_days.get(stage)
        if days is not None:
            harvest_date = add_days(sampling_date, days)
            iso_week = harvest_date.isocalendar()[1]

            offset = (iso_week - sampling_week + 1) if iso_week >= sampling_week else (iso_week + 52 - sampling_week + 1)
            if 1 <= offset <= 10:
                weekly_totals[offset] = weekly_totals.get(offset, 0) + scaled_count

    # ✅ Get actual harvested qty from Stock Entries for current sampling week (Cut stage)
    current_week_harvest = frappe.db.sql("""
        SELECT SUM(sed.qty)
        FROM `tabStock Entry` se
        JOIN `tabStock Entry Detail` sed ON sed.parent = se.name
        WHERE sed.item_code = %s
          AND sed.t_warehouse = %s
          AND WEEK(se.posting_date, 1) = %s
          AND se.docstatus = 1
    """, (variety, greenhouse, sampling_week))[0][0] or 0 

    cut_stage_days = growth_stage_days.get("Cut stage")
    if cut_stage_days is not None and current_week_harvest:
        harvest_date = add_days(sampling_date, cut_stage_days)
        iso_week = harvest_date.isocalendar()[1]

        offset = (iso_week - sampling_week + 1) if iso_week >= sampling_week else (iso_week + 52 - sampling_week + 1)
        if 1 <= offset <= 10:
            weekly_totals[offset] = weekly_totals.get(offset, 0) + current_week_harvest

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

    # ✅ Get last week's forecast (if exists)
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
        "custom_week_no": sampling_week,
        "custom_farm": samplings[0].get("custom_farm") if hasattr(samplings[0], "custom_farm") else None
    })

    for i in range(10):
        offset = i + 1
        iso_week = (sampling_week + i - 1) % 52 + 1
        expected = weekly_totals.get(offset) or 0

        # Determine last week's ISO week
        prev_week = iso_week - 1 if iso_week > 1 else 52

        # Default values
        last_week_harvest_val = 0
        last_week_forecast_val = 0

        # Populate last_week_harvest:
        if offset == 2:
            last_week_harvest_val = current_week_harvest
        else:
            last_week_harvest_val = frappe.db.sql("""
                SELECT SUM(sed.qty)
                FROM `tabStock Entry` se
                JOIN `tabStock Entry Detail` sed ON sed.parent = se.name
                WHERE sed.item_code = %s
                AND sed.t_warehouse = %s
                AND WEEK(se.posting_date, 1) = %s
                AND se.docstatus = 1
            """, (variety, greenhouse, prev_week))[0][0] or 0

        # Populate last_week_forecast only for offset = 1
        if offset == 1 and prev:
            last_doc = frappe.get_doc("Forecasting Form", prev[0].name)
            for r in last_doc.forecast_details:
                if r.week_no == sampling_week:
                    last_week_forecast_val = r.current_forecast or 0
                    break

        forecast.append("forecast_details", {
            "week_no": iso_week,
            "expected_production": expected,
            "last_week_harvest": last_week_harvest_val,
            "last_week_forecast": last_week_forecast_val,
            "current_forecast": None
        })

    forecast.insert(ignore_permissions=True)
    return forecast.name

def execute(filters=None):
    filters = filters or {}
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

    # ✅ Fetch rows aggregated at parent level
    data = frappe.db.sql(f"""
        SELECT
            bs.name AS "ID",
            bs.greenhouse AS "Greenhouse",
            bs.variety AS "Variety",
            bs.week_no AS "Week No.",
            bs.sample_bed_length * cc.bed_width AS "Sampling Area",
            bs.total_variety_area AS "Total Variety Area",
            bs.date AS "Sampling Date",
            bs.custom_farm AS "Farm",
            -- ✅ average across child rows
            AVG(bsg.rice_stage) AS "Rice Stage",
            AVG(bsg.ball_stage) AS "Ball Stage",
            AVG(bsg.colour_break_stage) AS "Colour Break Stage",
            AVG(bsg.full_colour_break_stage) AS "Full Colour Break Stage"
        FROM `tabBed Sampling Form` bs
        LEFT JOIN `tabCrop Cycle` cc
            ON cc.greenhouse = bs.greenhouse AND cc.variety = bs.variety
        LEFT JOIN `tabSampling Table` bsg
            ON bsg.parent = bs.name
        WHERE bs.docstatus = 1 {condition_sql}
        GROUP BY bs.name, bs.greenhouse, bs.variety, bs.week_no,
                 bs.sample_bed_length, cc.bed_width,
                 bs.total_variety_area, bs.date, bs.custom_farm
        ORDER BY bs.date DESC
    """, filters, as_dict=1)

    columns = [
        {"label": "ID", "fieldname": "ID", "fieldtype": "Link", "options": "Bed Sampling Form", "width": 120},
        {"label": "Farm", "fieldname": "Farm", "fieldtype": "Link", "options": "Farm", "width": 120},
        {"label": "Greenhouse", "fieldname": "Greenhouse", "fieldtype": "Link", "options": "Warehouse", "width": 120},
        {"label": "Variety", "fieldname": "Variety", "fieldtype": "Link", "options": "Item", "width": 120},
        {"label": "Week No.", "fieldname": "Week No.", "fieldtype": "Int", "width": 80},
        {"label": "Sampling Area", "fieldname": "Sampling Area", "fieldtype": "Float", "width": 100},
        {"label": "Total Variety Area", "fieldname": "Total Variety Area", "fieldtype": "Float", "width": 120},
        {"label": "Sampling Date", "fieldname": "Sampling Date", "fieldtype": "Date", "width": 100},
        {"label": "Rice Stage", "fieldname": "Rice Stage", "fieldtype": "Float", "width": 100},
        {"label": "Ball Stage", "fieldname": "Ball Stage", "fieldtype": "Float", "width": 100},
        {"label": "Colour Break Stage", "fieldname": "Colour Break Stage", "fieldtype": "Float", "width": 120},
        {"label": "Full Colour Break Stage", "fieldname": "Full Colour Break Stage", "fieldtype": "Float", "width": 150},
    ]

    # ✅ Add totals/averages row if there’s data
    if data:
        total_sampling_area = sum(d.get("Sampling Area") or 0 for d in data)
        total_variety_area = sum(d.get("Total Variety Area") or 0 for d in data)

        avg_rice_stage = round(sum(d.get("Rice Stage") or 0 for d in data) / len(data), 2)
        avg_ball_stage = round(sum(d.get("Ball Stage") or 0 for d in data) / len(data), 2)
        avg_colour_break_stage = round(sum(d.get("Colour Break Stage") or 0 for d in data) / len(data), 2)
        avg_full_colour_break_stage = round(sum(d.get("Full Colour Break Stage") or 0 for d in data) / len(data), 2)

        summary_row = {
            "ID": "➤ SUMMARY",
            "Farm": "",
            "Greenhouse": "",
            "Variety": "",
            "Week No.": "",
            "Sampling Area": total_sampling_area,
            "Total Variety Area": total_variety_area,
            "Sampling Date": "",
            "Rice Stage": avg_rice_stage,
            "Ball Stage": avg_ball_stage,
            "Colour Break Stage": avg_colour_break_stage,
            "Full Colour Break Stage": avg_full_colour_break_stage,
        }

        data.append(summary_row)

    return columns, data

