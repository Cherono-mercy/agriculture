import frappe

def execute(filters=None):
    filters = filters or {}
    conditions = ""
    sql_filters = {}

    if filters.get("greenhouse"):
        conditions += " AND f.greenhouse = %(greenhouse)s"
        sql_filters["greenhouse"] = filters.get("greenhouse")

    if filters.get("variety"):
        conditions += " AND f.variety = %(variety)s"
        sql_filters["variety"] = filters.get("variety")

    if filters.get("custom_week_no"):
        conditions += " AND f.custom_week_no = %(custom_week_no)s"
        sql_filters["custom_week_no"] = filters.get("custom_week_no")

    columns = [
        {"label": "Week No", "fieldname": "week_no", "fieldtype": "Int", "width": 80},
        {"label": "Greenhouse", "fieldname": "greenhouse", "fieldtype": "Link", "options": "Warehouse", "width": 120},
        {"label": "Variety", "fieldname": "variety", "fieldtype": "Link", "options": "Item", "width": 120},
        {"label": "Expected Production", "fieldname": "expected_production", "fieldtype": "Float", "width": 150},
    ]

    data = frappe.db.sql(f"""
        SELECT
            fd.week_no AS week_no,
            f.greenhouse AS greenhouse,
            f.variety AS variety,
            SUM(fd.expected_production) AS expected_production
        FROM `tabForecasting Form` f
        JOIN `tabForecasting Item` fd ON fd.parent = f.name
        WHERE f.docstatus < 2 {conditions}
        GROUP BY fd.week_no, f.greenhouse, f.variety
        ORDER BY fd.week_no, f.greenhouse, f.variety
    """, sql_filters, as_dict=1)

    return columns, data
