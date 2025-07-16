// Copyright (c) 2025, Frappe and contributors
// For license information, please see license.txt

frappe.query_reports["Bed Sampling Summary"] = {
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
      "fieldname": "week_no",
      "label": "Week No.",
      "fieldtype": "Int"
    }
  ],
  onload: function(report) {
    report.page.add_inner_button("Generate Forecasting Form", function() {
      let filters = report.get_values();
      if (!filters.greenhouse || !filters.variety || !filters.week_no) {
        frappe.msgprint("Please select Greenhouse, Variety, and Week No. before generating the forecasting form.");
        return;
      }

      frappe.call({
        method: "agriculture.agriculture.report.bed_sampling_summary.bed_sampling_summary.generate_forecasting_form",
        args: {
          greenhouse: filters.greenhouse,
          variety: filters.variety,
          week_no: filters.week_no
        },
        callback: function(r) {
          if (!r.exc && r.message) {
            frappe.set_route("Form", "Forecasting Form", r.message);
          }
        }
      });
    });
  }
};
