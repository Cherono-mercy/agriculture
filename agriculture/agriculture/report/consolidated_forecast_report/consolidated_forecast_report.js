// Copyright (c) 2025, Frappe and contributors
// For license information, please see license.txt

frappe.query_reports["Consolidated Forecast Report"] = {
	"filters": [
		{
			"fieldname": "greenhouse",
			"label": "Greenhouse",
			"fieldtype": "Link",
			"options": "Warehouse"
		},
		{
			"fieldname": "variety",
			"label": "Variety",
			"fieldtype": "Link",
			"options": "Item"
		},
		{
			"fieldname": "custom_week_no",
			"label": "Week No",
			"fieldtype": "Int"
		}
	]
};
