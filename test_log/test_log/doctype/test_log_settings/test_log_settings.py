# Copyright (c) 2026, Aerele and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from test_log.constants import vocabulary

FALLBACK_ROLES = ("Tester", "System Manager")
MIN_SYNC_INTERVAL = 15


class TestLogSettings(Document):
	def validate(self):
		if self.sync_interval_seconds and self.sync_interval_seconds < MIN_SYNC_INTERVAL:
			self.sync_interval_seconds = MIN_SYNC_INTERVAL

	def on_update(self):
		frappe.clear_document_cache(self.doctype, self.name)


def get_settings() -> "TestLogSettings":
	"""The single, straight from cache. Falls back to field defaults before the first save."""
	return frappe.get_cached_doc("Test Log Settings")


def allowed_roles(settings=None) -> set[str]:
	settings = settings or get_settings()
	roles = {row.role for row in (settings.allowed_roles or []) if row.role}
	return roles or set(FALLBACK_ROLES)


def is_enabled_for(user: str | None = None, settings=None) -> bool:
	"""Whether this user should be offered the capture widget."""
	user = user or frappe.session.user
	if user in ("Guest", ""):
		return False

	settings = settings or get_settings()
	if not settings.enable_tester_mode:
		return False

	if not frappe.has_permission("Test Log", "create", user=user):
		return False

	if settings.available_to_all_users:
		return True

	return bool(allowed_roles(settings) & set(frappe.get_roles(user)))


def developer_choices() -> list[dict]:
	"""Who a tester can hand a finding to, straight from the capture panel.

	Built with the query builder rather than get_all, because reading a child table
	like Has Role directly is not something a plain Tester is allowed to do.
	"""
	has_role = frappe.qb.DocType("Has Role")
	user = frappe.qb.DocType("User")

	return (
		frappe.qb.from_(has_role)
		.join(user)
		.on(has_role.parent == user.name)
		.select(user.name, user.full_name)
		.distinct()
		.where((has_role.role == "Developer") & (has_role.parenttype == "User") & (user.enabled == 1))
		.orderby(user.full_name)
		.limit(100)
		.run(as_dict=True)
	)


def widget_config(user: str | None = None) -> dict:
	"""Everything the browser widget needs to run — including while offline.

	Shipped through the boot info on desk pages, and fetched over the API elsewhere.
	The widget caches this payload, so it keeps working after the connection drops.
	"""
	user = user or frappe.session.user

	try:
		settings = get_settings()
	except Exception:
		# Site not migrated yet — never let this break a page load.
		frappe.log_error(title="Test Log widget config")
		return {"enabled": False}

	if not is_enabled_for(user, settings):
		return {"enabled": False}

	return {
		"enabled": True,
		"user": {"name": user, "full_name": frappe.utils.get_fullname(user)},
		"tools": {
			"screenshot": bool(settings.enable_screenshot),
			"recording": bool(settings.enable_screen_recording),
			"snip": bool(settings.enable_snipping),
			"attach": bool(settings.enable_file_attach),
			"recording_limit_seconds": settings.recording_limit_seconds or 0,
			"max_attachment_mb": settings.max_attachment_mb or 50,
			"private_uploads": bool(settings.private_attachments),
		},
		"context": {
			"page": bool(settings.capture_page_context),
			"console": bool(settings.capture_console_errors),
			"console_limit": settings.console_error_limit or 20,
		},
		"offline": {
			"enabled": bool(settings.enable_offline_queue),
			"retry_seconds": max(settings.sync_interval_seconds or 60, MIN_SYNC_INTERVAL),
		},
		"defaults": {
			"product": settings.default_product,
			"test_run": settings.default_test_run,
			"severity": settings.default_severity or "Medium",
			"test_type": settings.default_test_type or "Functional",
		},
		"developers": developer_choices(),
		"products": frappe.get_all(
			"Test Product",
			filters={"is_active": 1},
			fields=["name", "product_name"],
			order_by="product_name asc",
			limit=50,
		),
		"runs": frappe.get_all(
			"Test Run",
			filters={"status": ["!=", "Signed Off"]},
			fields=["name", "title", "product", "build_version"],
			order_by="modified desc",
			limit=25,
		),
		"vocabulary": vocabulary(),
	}
