app_name = "test_log"
app_title = "Test Log"
app_publisher = "Aerele"
app_description = "Testing logs with screenshots, recordings and status tracking"
app_email = "kurinji@aerele.in"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Installation
# ------------------

before_install = "test_log.install.before_install"
after_install = "test_log.install.after_install"

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "test_log",
# 		"logo": "/assets/test_log/logo.png",
# 		"title": "Test Log",
# 		"route": "/test_log",
# 		"has_permission": "test_log.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# The tester capture widget. Plain files rather than a bundle, so a site can be set up
# and used offline without running a build first. Load order matters: core registers the
# namespace, widget boots once everything else is on the page.
_TESTER_WIDGET_JS = [
	"/assets/test_log/js/tester/core.js",
	"/assets/test_log/js/tester/store.js",
	"/assets/test_log/js/tester/capture.js",
	"/assets/test_log/js/tester/annotate.js",
	"/assets/test_log/js/tester/panel.js",
	"/assets/test_log/js/tester/widget.js",
]
_TESTER_WIDGET_CSS = ["/assets/test_log/css/tester.css"]

app_include_js = _TESTER_WIDGET_JS
app_include_css = _TESTER_WIDGET_CSS

# Portal pages are part of what gets tested too — the widget keeps itself hidden
# unless the logged-in user is allowed to see it.
web_include_js = _TESTER_WIDGET_JS
web_include_css = _TESTER_WIDGET_CSS

# Hands the widget its settings with the page, so it can draw itself before the first
# request — and still work once the connection drops.
extend_bootinfo = "test_log.boot.boot_session"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "test_log/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "test_log/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "test_log.utils.jinja_methods",
# 	"filters": "test_log.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "test_log.install.before_install"
# after_install = "test_log.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "test_log.uninstall.before_uninstall"
# after_uninstall = "test_log.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "test_log.utils.before_app_install"
# after_app_install = "test_log.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "test_log.utils.before_app_uninstall"
# after_app_uninstall = "test_log.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "test_log.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "test_log.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"test_log.tasks.all"
# 	],
# 	"daily": [
# 		"test_log.tasks.daily"
# 	],
# 	"hourly": [
# 		"test_log.tasks.hourly"
# 	],
# 	"weekly": [
# 		"test_log.tasks.weekly"
# 	],
# 	"monthly": [
# 		"test_log.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "test_log.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "test_log.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "test_log.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "test_log.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["test_log.utils.before_request"]
# after_request = ["test_log.utils.after_request"]

# Job Events
# ----------
# before_job = ["test_log.utils.before_job"]
# after_job = ["test_log.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"test_log.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

