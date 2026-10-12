"""Regressions for evidence access, scoped sharing, exports and background actions."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from test_log.api.capture import log_entry
from test_log.api.excel import build_run_sheet
from test_log.api.report import _file_content, build_run_report
from test_log.api.sharing import share_run
from test_log.jobs import run_action
from test_log.tasks import notify_overdue_logs, send_daily_digest
from test_log.test_log.doctype.test_log.test_log import bulk_set_status, set_status
from test_log.tests.utils import make_log, make_product, make_run


class TestHardening(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.product = make_product()
		self.run = make_run(self.product)
		self.developer = self.user("Developer")
		self.tester = self.user("Tester")

	def tearDown(self):
		frappe.set_user("Administrator")

	def user(self, role):
		name = f"hardening-{frappe.generate_hash(length=10)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": name,
				"first_name": role,
				"send_welcome_email": 0,
				"roles": [{"role": role}],
			}
		).insert()
		return name

	def file(self, **values):
		return frappe.get_doc(
			{
				"doctype": "File",
				"file_name": frappe.generate_hash() + ".png",
				"content": b"private evidence " + frappe.generate_hash().encode(),
				"is_private": 1,
				**values,
			}
		).insert()

	def test_foreign_private_evidence_is_rejected_and_never_read(self):
		file = self.file()
		log = make_log(self.product, self.run)
		frappe.set_user(self.tester)
		log.append("attachments", {"attachment_type": "Screenshot", "file_url": file.file_url})
		with self.assertRaises(frappe.PermissionError):
			log.save()
		with patch("builtins.open") as open_file:
			self.assertIsNone(_file_content(file))
			open_file.assert_not_called()

	def test_owned_attached_and_explicitly_readable_files_are_allowed(self):
		attached = self.file(attached_to_doctype="Test Run", attached_to_name=self.run.name)
		log = make_log(self.product, self.run)
		own_log_file = self.file(attached_to_doctype="Test Log", attached_to_name=log.name)
		frappe.set_user(self.tester)
		owned = self.file()
		for file in (owned, attached, own_log_file):
			log.append("attachments", {"attachment_type": "Screenshot", "file_url": file.file_url})
		log.save()
		self.assertEqual(len(log.attachments), 3)

	def test_unknown_file_is_rejected(self):
		log = make_log(self.product, self.run)
		log.append("attachments", {"attachment_type": "Screenshot", "file_url": "/private/files/unknown.png"})
		with self.assertRaises(frappe.PermissionError):
			log.save()

	def test_developer_only_sees_shared_logs_and_cannot_rewrite_tester_fields(self):
		private = make_log(self.product, self.run)
		shared = make_log(self.product, self.run, assigned_developer=self.developer)
		frappe.set_user(self.developer)
		self.assertFalse(frappe.has_permission("Test Log", "read", doc=private.name))
		self.assertTrue(frappe.has_permission("Test Log", "write", doc=shared.name))
		visible_names = frappe.get_list("Test Log", pluck="name")
		self.assertIn(shared.name, visible_names)
		self.assertNotIn(private.name, visible_names)
		set_status(shared.name, "Ongoing")
		shared.reload()
		shared.subject = "Rewritten"
		with self.assertRaises(frappe.PermissionError):
			shared.save()

	def test_log_joining_shared_run_inherits_access(self):
		share_run(self.run.name, self.developer, can_write=1)
		new_log = make_log(self.product, self.run)
		moved = make_log(self.product)
		moved.test_run = self.run.name
		moved.save()
		frappe.set_user(self.developer)
		for log in (new_log, moved):
			self.assertTrue(frappe.has_permission("Test Log", "read", doc=log.name))
			self.assertTrue(frappe.has_permission("Test Log", "write", doc=log.name))

	def test_run_exports_exclude_unreadable_logs(self):
		hidden = make_log(self.product, self.run, subject="Secret finding")
		visible = make_log(self.product, self.run, assigned_developer=self.developer)
		frappe.share.add("Test Run", self.run.name, self.developer, read=1)
		frappe.set_user(self.developer)
		with (
			patch("test_log.api.report._write_logs") as write_logs,
			patch("test_log.api.report.deliver", return_value={}),
		):
			result = build_run_report(self.run.name)
			self.assertEqual(write_logs.call_args.args[1], [visible.name])
			self.assertEqual(result["skipped"], 1)
		with (
			patch("test_log.api.excel._rows", return_value=[]) as rows,
			patch("test_log.api.excel.deliver", return_value={}),
		):
			result = build_run_sheet(self.run.name)
			self.assertEqual(rows.call_args.args[0], [visible.name])
			self.assertEqual(result["skipped"], 1)
		self.assertNotEqual(hidden.name, visible.name)

	def test_client_id_retry_checks_read_permission(self):
		log = make_log(self.product, self.run, client_id=frappe.generate_hash())
		with patch("frappe.has_permission", side_effect=lambda dt, ptype, **kw: self._deny_read(ptype)):
			with self.assertRaises(frappe.PermissionError):
				log_entry({"client_id": log.client_id})

	def _deny_read(self, ptype):
		if ptype == "read":
			raise frappe.PermissionError
		return True

	def test_digest_severity_order_before_truncation(self):
		rows = [
			frappe._dict(
				name=str(i), subject=str(i), severity=s, status="Open", assigned_developer=self.developer
			)
			for i, s in enumerate(["Low"] * 26 + ["Medium", "High", "Critical"])
		]
		with (
			patch("test_log.tasks.frappe.get_all", return_value=rows),
			patch("test_log.tasks._notify") as notify,
		):
			send_daily_digest()
			body = notify.call_args.args[4]
			self.assertLess(body.index("Critical"), body.index("High"))
			self.assertLess(body.index("High"), body.index("Medium"))
			self.assertLess(body.index("Medium"), body.index("Low"))

	def test_overdue_reminders_only_on_day_1_3_7(self):
		rows = [
			frappe._dict(
				name=str(days),
				subject="Late",
				status="Open",
				severity="High",
				assigned_developer=self.developer,
				target_date=add_days(nowdate(), -days),
			)
			for days in range(1, 9)
		]
		with (
			patch("test_log.tasks.frappe.get_all", return_value=rows),
			patch("test_log.tasks._notify") as notify,
		):
			notify_overdue_logs()
			self.assertEqual([call.args[2] for call in notify.call_args_list], ["1", "3", "7"])

	def test_large_action_queues_without_saving(self):
		with (
			patch("frappe.enqueue") as enqueue,
			patch("test_log.test_log.doctype.test_log.test_log.set_status") as save,
		):
			result = bulk_set_status([f"TL-{i}" for i in range(51)], "Ongoing")
			self.assertTrue(result["queued"])
			save.assert_not_called()
			self.assertEqual(enqueue.call_args.kwargs["requester"], "Administrator")

	def test_worker_rechecks_permissions_as_requester(self):
		log = make_log(self.product, self.run)
		with patch("frappe.publish_realtime") as publish:
			run_action(
				"bulk_set_status", {"names": [log.name], "status": "Ongoing"}, self.developer, "test-job"
			)
			result = publish.call_args.args[1]["result"]
			self.assertFalse(result["updated"])
			self.assertEqual(len(result["skipped"]), 1)
		self.assertEqual(frappe.session.user, "Administrator")

	def test_read_only_run_share_does_not_downgrade_assignment(self):
		share_run(self.run.name, self.developer, can_write=0)
		read_only = make_log(self.product, self.run)
		assigned = make_log(self.product, self.run, assigned_developer=self.developer)
		frappe.set_user(self.developer)
		self.assertTrue(frappe.has_permission("Test Log", "read", doc=read_only.name))
		self.assertFalse(frappe.has_permission("Test Log", "write", doc=read_only.name))
		self.assertTrue(frappe.has_permission("Test Log", "write", doc=assigned.name))

	def test_developer_can_resolve_with_evidence_but_cannot_replace_it(self):
		log = make_log(self.product, self.run, assigned_developer=self.developer)
		file = self.file(attached_to_doctype="Test Log", attached_to_name=log.name)
		log.append("attachments", {"attachment_type": "Screenshot", "file_url": file.file_url})
		log.save()
		frappe.set_user(self.developer)
		set_status(log.name, "Ongoing")
		set_status(log.name, "Fixed", resolution="Patched the save handler")
		with self.assertRaises(frappe.PermissionError):
			set_status(log.name, "Completed")
		log.reload()
		log.attachments = []
		with self.assertRaises(frappe.PermissionError):
			log.save()

	def test_report_rebuild_only_on_status_or_membership_changes(self):
		from test_log.tests.utils import settings_with

		log = make_log(self.product, self.run)
		with settings_with(auto_attach_run_report=1), patch("frappe.enqueue") as enqueue:
			log.subject = "Updated wording"
			log.save()
			enqueue.assert_not_called()
			log.status = "Ongoing"
			log.save()
			jobs = [
				call
				for call in enqueue.call_args_list
				if call.args[0] == "test_log.api.report.refresh_run_report"
			]
			self.assertEqual(len(jobs), 1)

	def test_read_only_export_stays_private(self):
		from test_log.api.artifacts import deliver

		frappe.share.add("Test Run", self.run.name, self.developer, read=1)
		frappe.set_user(self.developer)
		result = deliver(b"read only report", self.run, "read-only.txt", 1)
		self.assertFalse(result["attached"])
		file = frappe.get_doc("File", {"file_url": result["file_url"]})
		self.assertFalse(file.attached_to_name)
		self.assertEqual(file.owner, self.developer)

	def test_large_export_queues(self):
		from test_log.api.report import build_selection_report

		with patch("frappe.enqueue") as enqueue:
			result = build_selection_report([f"TL-{i}" for i in range(51)])
			self.assertTrue(result["queued"])
			self.assertEqual(enqueue.call_args.kwargs["operation"], "build_selection_report")

	def test_unique_retry_rolls_back_only_its_savepoint(self):
		from test_log.test_log.doctype.test_log.test_log import TestLog

		log = make_log(self.product, self.run, client_id=frappe.generate_hash())
		original_get = frappe.db.get_value
		lookups = []

		def get_value(doctype, filters=None, *args, **kwargs):
			if (
				doctype == "Test Log"
				and isinstance(filters, dict)
				and filters.get("client_id") == log.client_id
			):
				lookups.append(True)
				return None if len(lookups) == 1 else log.name
			return original_get(doctype, filters, *args, **kwargs)

		with (
			patch.object(frappe.db, "get_value", side_effect=get_value),
			patch.object(TestLog, "insert", side_effect=frappe.UniqueValidationError),
			patch.object(frappe.db, "rollback", wraps=frappe.db.rollback) as rollback,
		):
			result = log_entry(
				{"client_id": log.client_id, "product": self.product.name, "description": "Retry"}
			)
			self.assertTrue(result["duplicate"])
			self.assertIn("save_point", rollback.call_args.kwargs)
			self.assertTrue(frappe.db.exists("Test Log", log.name))
