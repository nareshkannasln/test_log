import frappe
from frappe import _
from frappe.model.document import Document


class TestLogIntegration(Document):
	def validate(self):
		if self.enable_github and not (
			self.github_user
			and self.get_password("github_token", raise_exception=False)
			and self.get_password("webhook_secret", raise_exception=False)
		):
			frappe.throw(_("GitHub requires a token, webhook secret and integration user."))
		if self.enable_email and not (self.email_account and self.email_product and self.email_tester):
			frappe.throw(_("Email capture requires an Email Account, product and tester."))
