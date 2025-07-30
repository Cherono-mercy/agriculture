# Copyright (c) 2025, Frappe and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class BedSamplingForm(Document):
	pass

@frappe.whitelist()
def get_sampling_defaults(greenhouse, variety, sample_bed_length=4):
    sample_bed_length = float(sample_bed_length or 4)

    crop = frappe.get_all(
        "Crop Cycle",
        filters={"greenhouse": greenhouse, "variety": variety},
        fields=["bed_width", "area"]
    )

    if not crop:
        frappe.throw("No Crop Cycle found for selected Greenhouse and Variety.")

    bed_width = crop[0].bed_width or 0
    total_area = crop[0].area or 0
    sampling_area = bed_width * sample_bed_length

    return {
        "sampling_area": sampling_area,
        "total_variety_area": total_area
    }

