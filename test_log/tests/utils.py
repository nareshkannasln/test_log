# Copyright (c) 2026, Aerele and contributors
# See license.txt

"""Fixtures the tests share: a product, a run, a log, and a way to pin the settings.

Test Log Settings is a Single read through the document cache, so a test that wants
the status flow enforced (or not) has to write the value and clear that cache — doing
it in one place keeps every test honest about what it is actually testing.
"""

from contextlib import contextmanager

import frappe

PRODUCT = "_Test Product"


def make_product(name: str = PRODUCT, default_developer: str | None = None):
	if frappe.db.exists("Test Product", name):
		product = frappe.get_doc("Test Product", name)
		if product.default_developer != default_developer:
			product.default_developer = default_developer
			product.save()
		return product

	return frappe.get_doc(
		{
			"doctype": "Test Product",
			"product_name": name,
			"is_active": 1,
			"default_developer": default_developer,
		}
	).insert()


def make_run(product=None, **kwargs):
	product = product or make_product()

	values = {
		"doctype": "Test Run",
		"title": "_Test Run",
		"product": product.name,
		"build_version": "1.0.0",
		"status": "In Progress",
	}
	values.update(kwargs)

	return frappe.get_doc(values).insert()


def make_log(product=None, run=None, **kwargs):
	product = product or make_product()

	values = {
		"doctype": "Test Log",
		"subject": "_Test finding",
		"product": product.name,
		"test_run": run.name if run else None,
		"severity": "Medium",
		"test_type": "Functional",
		"status": "Open",
		"tester": frappe.session.user,
	}
	values.update(kwargs)

	return frappe.get_doc(values).insert()


@contextmanager
def settings_with(**values):
	"""Run a block with Test Log Settings pinned to these values, then put them back."""
	previous = {}

	for fieldname, value in values.items():
		previous[fieldname] = frappe.db.get_single_value("Test Log Settings", fieldname)
		frappe.db.set_single_value("Test Log Settings", fieldname, value)

	frappe.clear_document_cache("Test Log Settings", "Test Log Settings")

	try:
		yield
	finally:
		for fieldname, value in previous.items():
			frappe.db.set_single_value("Test Log Settings", fieldname, value)
		frappe.clear_document_cache("Test Log Settings", "Test Log Settings")
