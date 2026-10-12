import hashlib
import hmac
import json
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from test_log.integrations import (
	create_github_issue,
	email_to_log,
	github_webhook,
	process_github_event,
	validate_git_links,
)
from test_log.tests.utils import make_log, make_product


class TestIntegrations(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.product = make_product()
		self.product.repository_url = "https://github.com/example/application"
		self.product.save()
		self.log = make_log(self.product)
		self.config = frappe._dict(
			enable_github=1, github_user="Administrator", get_password=lambda *a, **kw: "test-secret"
		)

	def test_issue_creation_is_idempotent(self):
		with patch(
			"test_log.integrations.github",
			side_effect=[{"items": []}, {"html_url": "https://github.com/example/application/issues/1"}],
		) as api:
			first = create_github_issue(self.log.name)
			second = create_github_issue(self.log.name)
			self.assertEqual(first, second)
			self.assertEqual(api.call_count, 2)

	def test_invalid_signature_never_queues_work(self):
		with (
			patch("test_log.integrations.settings", return_value=self.config),
			patch("frappe.request", SimpleNamespace(get_data=lambda: b"{}"), create=True),
			patch("frappe.get_request_header", return_value="bad"),
			patch("frappe.enqueue") as enqueue,
		):
			with self.assertRaises(frappe.PermissionError):
				github_webhook(self.product.name)
			enqueue.assert_not_called()

	def test_valid_signature_and_repository_queue_delivery(self):
		body = json.dumps({"repository": {"full_name": "example/application"}}).encode()
		headers = {
			"X-Hub-Signature-256": "sha256=" + hmac.new(b"test-secret", body, hashlib.sha256).hexdigest(),
			"X-GitHub-Delivery": frappe.generate_hash(),
			"X-GitHub-Event": "pull_request",
		}
		with (
			patch("test_log.integrations.settings", return_value=self.config),
			patch("frappe.request", SimpleNamespace(get_data=lambda: body), create=True),
			patch("frappe.get_request_header", side_effect=headers.get),
			patch("frappe.enqueue") as enqueue,
		):
			self.assertTrue(github_webhook(self.product.name)["queued"])
			self.assertEqual(
				enqueue.call_args.kwargs["payload"]["repository"]["full_name"], "example/application"
			)

	def test_merge_then_release_sets_status_and_build_once(self):
		payload = {
			"repository": {"full_name": "example/application"},
			"action": "closed",
			"pull_request": {
				"number": 8,
				"title": "Fix " + self.log.name,
				"merged": True,
				"merge_commit_sha": "a" * 40,
			},
		}
		delivery = frappe.generate_hash()
		with patch("test_log.integrations.settings", return_value=self.config):
			process_github_event(self.product.name, "pull_request", delivery, payload)
			process_github_event(self.product.name, "pull_request", delivery, payload)
			self.log.reload()
			self.assertEqual(self.log.status, "Fixed")
			self.assertEqual(self.log.github_merge_sha, "a" * 40)
			self.assertFalse(self.log.fixed_in_build)
			with patch("test_log.integrations.github", return_value={"status": "ahead"}):
				process_github_event(
					self.product.name,
					"release",
					frappe.generate_hash(),
					{
						"repository": payload["repository"],
						"action": "published",
						"release": {"tag_name": "v2.0"},
					},
				)
			self.log.reload()
			self.assertEqual(self.log.fixed_in_build, "v2.0")

	def test_unmerged_pr_and_wrong_product_do_not_change_log(self):
		with patch("test_log.integrations.settings", return_value=self.config):
			process_github_event(
				self.product.name,
				"pull_request",
				frappe.generate_hash(),
				{
					"repository": {"full_name": "example/application"},
					"action": "closed",
					"pull_request": {"merged": False, "title": self.log.name},
				},
			)
		self.log.reload()
		self.assertEqual(self.log.status, "Open")
		self.log.github_pr_url = "https://github.com/other/repo/pull/1"
		with self.assertRaises(frappe.ValidationError):
			validate_git_links(self.log)

	def test_email_capture_uses_configured_identity_and_idempotency(self):
		config = frappe._dict(
			enable_email=1,
			email_account="Support",
			email_product=self.product.name,
			email_tester="Administrator",
		)
		comm = frappe._dict(
			name="email-unit",
			email_account="Support",
			sent_or_received="Received",
			reference_doctype=None,
			sender="customer@example.com",
			content="<p>Broken screen</p>",
			subject="Support request",
		)
		with (
			patch("test_log.integrations.settings", return_value=config),
			patch("frappe.get_doc", return_value=comm),
			patch("test_log.api.capture.log_entry", return_value=frappe._dict(name=self.log.name)) as create,
			patch("frappe.db.set_value"),
		):
			email_to_log(comm.name)
			entry = create.call_args.args[0]
			self.assertEqual(entry["client_id"], "email:" + comm.name)
			self.assertEqual(entry["product"], self.product.name)
			self.assertIn("Broken screen", entry["description"])
