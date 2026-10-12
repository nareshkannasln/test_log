import frappe
from frappe import _
from frappe.model.document import Document


class TestEvidenceComment(Document):
	def validate(self):
		log = frappe.get_doc("Test Log", self.test_log)
		log.check_permission("read")
		if not any(row.name == self.evidence_row for row in log.attachments):
			frappe.throw(_("Choose evidence belonging to this log."))
		if self.reply_to:
			parent = frappe.get_doc(self.doctype, self.reply_to)
			if parent.test_log != self.test_log or parent.evidence_row != self.evidence_row:
				frappe.throw(_("A reply must stay in the same evidence thread."))
		if not (self.content or "").strip():
			frappe.throw(_("Write a comment."))
		for user in (self.mentions or "").split(","):
			if user.strip() and not frappe.has_permission("Test Log", "read", doc=log, user=user.strip()):
				frappe.throw(_("Mentioned users must already have access to the log."))

	def after_insert(self):
		from test_log.test_log.doctype.test_log.test_log import notify

		users = {u.strip() for u in (self.mentions or "").split(",") if u.strip()} - {frappe.session.user}
		if users:
			notify(
				frappe.get_doc("Test Log", self.test_log),
				list(users),
				_("You were mentioned on evidence in {0}").format(self.test_log),
				frappe.utils.escape_html(self.content),
			)


@frappe.whitelist()
def add_evidence_comment(
	test_log: str,
	evidence_row: str,
	content: str,
	reply_to: str | None = None,
	mentions: str = "",
	annotation: str = "",
):
	frappe.has_permission("Test Log", "read", doc=test_log, throw=True)
	doc = frappe.get_doc(
		{
			"doctype": "Test Evidence Comment",
			"test_log": test_log,
			"evidence_row": evidence_row,
			"content": content,
			"reply_to": reply_to,
			"mentions": mentions,
			"annotation": annotation,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


@frappe.whitelist()
def get_evidence_comments(test_log: str, evidence_row: str):
	frappe.has_permission("Test Log", "read", doc=test_log, throw=True)
	return frappe.get_all(
		"Test Evidence Comment",
		filters={"test_log": test_log, "evidence_row": evidence_row},
		fields=["name", "owner", "creation", "content", "reply_to", "annotation", "mentions"],
		order_by="creation asc",
	)


def has_permission(doc, user=None, permission_type=None, **kwargs):
	return frappe.has_permission("Test Log", "read", doc=doc.test_log, user=user)


def permission_query_conditions(user=None):
	names = frappe.get_list("Test Log", pluck="name", limit=0, user=user or frappe.session.user)
	return "`tabTest Evidence Comment`.`test_log` in ({})".format(
		",".join(frappe.db.escape(name) for name in names) or "NULL"
	)
