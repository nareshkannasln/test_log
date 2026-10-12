"""Opt-in GitHub and inbound mail integrations. Credentials are administrator-only."""

import hashlib
import hmac
import re
from urllib.parse import quote, urlparse

import frappe
import requests
from frappe import _
from frappe.utils import escape_html


def settings():
	return frappe.get_single("Test Log Integration")


def repository(product):
	url = frappe.db.get_value("Test Product", product, "repository_url") or ""
	parsed = urlparse(url)
	path = parsed.path.strip("/").removesuffix(".git")
	if (
		parsed.scheme != "https"
		or parsed.netloc != "github.com"
		or not re.fullmatch(r"[\w.-]+/[\w.-]+", path)
	):
		frappe.throw(_("Set the product repository to https://github.com/owner/repository."))
	return path


def github(method, path, **kwargs):
	config = settings()
	if not config.enable_github:
		frappe.throw(_("Enable GitHub in Test Log Integration first."))
	token = config.get_password("github_token", raise_exception=False)
	if not token:
		frappe.throw(_("Configure a GitHub token first."))
	response = requests.request(
		method,
		"https://api.github.com/" + path,
		headers={
			"Authorization": "Bearer " + token,
			"Accept": "application/vnd.github+json",
			"X-GitHub-Api-Version": "2022-11-28",
		},
		timeout=30,
		**kwargs,
	)
	if not response.ok:
		frappe.throw(
			_("GitHub returned HTTP {0}. Check integration permissions and configuration.").format(
				response.status_code
			)
		)
	return response.json()


def validate_git_links(log):
	for key, segment in (("github_pr_url", "pull"), ("github_commit_url", "commit")):
		url = log.get(key)
		if not url:
			continue
		repo = repository(log.product)
		suffix = r"\d+" if segment == "pull" else r"[0-9a-fA-F]{7,40}"
		if not re.fullmatch(r"https://github\.com/" + re.escape(repo) + "/" + segment + "/" + suffix, url):
			frappe.throw(_("Git links must point to this product's repository."))


@frappe.whitelist()
def create_github_issue(test_log: str):
	frappe.db.get_value("Test Log", test_log, "name", for_update=True)
	log = frappe.get_doc("Test Log", test_log)
	log.check_permission("write")
	if log.github_issue_url:
		return log.github_issue_url
	repo = repository(log.product)
	marker = f"<!-- test-log:{frappe.local.site}:{log.name} -->"
	# Recover a prior successful POST if the HTTP response or DB commit was lost.
	existing = github("GET", "search/issues", params={"q": f'repo:{repo} is:issue "{log.name}" in:title'})
	for item in existing.get("items", []):
		if marker in (item.get("body") or ""):
			log.db_set("github_issue_url", item["html_url"])
			return item["html_url"]
	from test_log.api.artifacts import plain_text

	body = (
		marker
		+ "\n\n"
		+ "\n\n".join(
			f"### {label}\n{plain_text(log.get(field))}"
			for label, field in (
				("Steps", "steps_to_reproduce"),
				("Expected", "expected_result"),
				("Actual", "actual_result"),
			)
		)
	)
	issue = github("POST", f"repos/{repo}/issues", json={"title": f"{log.name}: {log.subject}", "body": body})
	log.db_set("github_issue_url", issue["html_url"])
	return issue["html_url"]


@frappe.whitelist(allow_guest=True, methods=["POST"])
def github_webhook(product: str):
	config = settings()
	secret = config.get_password("webhook_secret", raise_exception=False)
	raw = frappe.request.get_data()
	if len(raw) > 1024 * 1024:
		frappe.throw(_("Webhook payload too large."))
	signature = frappe.get_request_header("X-Hub-Signature-256") or ""
	if (
		not config.enable_github
		or not secret
		or not hmac.compare_digest(
			signature, "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
		)
	):
		frappe.throw(_("Invalid webhook signature."), frappe.PermissionError)
	payload = frappe.parse_json(raw.decode())
	repo = repository(product)
	if payload.get("repository", {}).get("full_name", "").lower() != repo.lower():
		frappe.throw(_("Webhook repository does not match this product."), frappe.PermissionError)
	event = frappe.get_request_header("X-GitHub-Event")
	if event not in ("pull_request", "release"):
		return {"ignored": True}
	delivery = frappe.get_request_header("X-GitHub-Delivery")
	if not delivery or len(delivery) > 140:
		frappe.throw(_("Missing webhook delivery ID."))
	frappe.enqueue(
		"test_log.integrations.process_github_event",
		queue="long",
		enqueue_after_commit=True,
		product=product,
		event=event,
		delivery=delivery,
		payload=payload,
	)
	return {"queued": True}


def process_github_event(product, event, delivery, payload):
	config = settings()
	if not config.enable_github:
		return
	repo = repository(product)
	if payload.get("repository", {}).get("full_name", "").lower() != repo.lower():
		frappe.throw(_("Repository mismatch."))
	acting_user = config.github_user
	if not acting_user or acting_user == "Guest" or not frappe.db.get_value("User", acting_user, "enabled"):
		frappe.throw(_("Configure an enabled GitHub integration user."))
	previous_user = frappe.session.user
	frappe.set_user(acting_user)
	try:
		# Insert before effects. The unique key serializes retries, and rolls back with failures.
		if frappe.db.exists("Test Log Webhook Delivery", {"delivery_id": delivery}):
			return
		frappe.get_doc(
			{
				"doctype": "Test Log Webhook Delivery",
				"delivery_id": delivery,
				"repository": repo,
				"event": event,
			}
		).insert(ignore_permissions=True)
		if (
			event == "pull_request"
			and payload.get("action") == "closed"
			and payload.get("pull_request", {}).get("merged")
		):
			pr = payload["pull_request"]
			text = (pr.get("title") or "") + "\n" + (pr.get("body") or "")
			for name in set(re.findall(r"\bTL-\d{4}-\d+\b", text)):
				if not frappe.db.exists("Test Log", {"name": name, "product": product}):
					continue
				log = frappe.get_doc("Test Log", name)
				log.check_permission("write")
				if log.status in ("Completed", "Won't Fix"):
					continue
				log.github_pr_url = f"https://github.com/{repo}/pull/{int(pr['number'])}"
				log.status = "Fixed"
				log.flags.ignore_status_flow = True
				log.save()
				log.db_set("github_merge_sha", pr.get("merge_commit_sha"))
		elif event == "release" and payload.get("action") == "published":
			tag = payload.get("release", {}).get("tag_name")
			if not tag:
				return
			for name in frappe.get_list(
				"Test Log",
				filters={
					"product": product,
					"github_merge_sha": ["is", "set"],
					"fixed_in_build": ["is", "not set"],
					"status": ["in", ["Fixed", "Completed"]],
				},
				pluck="name",
				limit=0,
			):
				log = frappe.get_doc("Test Log", name)
				log.check_permission("write")
				comparison = github(
					"GET",
					f"repos/{repo}/compare/{quote(log.github_merge_sha, safe='')}...{quote(tag, safe='')}",
				)
				if comparison.get("status") in ("ahead", "identical"):
					log.fixed_in_build = tag
					log.save()
	finally:
		frappe.set_user(previous_user)


def on_communication(doc, method=None):
	if doc.communication_medium != "Email" or doc.sent_or_received != "Received" or doc.reference_doctype:
		return
	config = settings()
	if config.enable_email and doc.email_account == config.email_account:
		frappe.enqueue(
			"test_log.integrations.email_to_log", communication=doc.name, enqueue_after_commit=True
		)


def email_to_log(communication):
	config = settings()
	comm = frappe.get_doc("Communication", communication)
	if (
		not config.enable_email
		or comm.email_account != config.email_account
		or comm.sent_or_received != "Received"
		or comm.reference_doctype
	):
		return
	user = config.email_tester
	if not user or user == "Guest" or not frappe.db.get_value("User", user, "enabled"):
		frappe.throw(_("Configure an enabled inbound email tester."))
	previous_user = frappe.session.user
	frappe.set_user(user)
	try:
		from test_log.api.artifacts import plain_text
		from test_log.api.capture import log_entry

		result = log_entry(
			{
				"client_id": "email:" + comm.name,
				"subject": (comm.subject or _("Support email"))[:140],
				"product": config.email_product,
				"description": f"From: {comm.sender}\n\n{plain_text(comm.content)}",
			}
		)
		# Store the source link without copying arbitrary private mail attachments.
		frappe.db.set_value(
			"Communication", comm.name, {"reference_doctype": "Test Log", "reference_name": result.name}
		)
		return result.name
	finally:
		frappe.set_user(previous_user)
