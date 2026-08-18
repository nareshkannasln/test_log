# Copyright (c) 2026, Aerele and contributors
# For license information, please see license.txt

"""The app's shared vocabulary: statuses, how they move, and the pick lists.

The Python controllers and the browser widget both read from here — the widget gets
its copy through the boot info — so the two can never drift apart.
"""

OPEN_STATUSES = ("Open", "Reopened", "Needs Info")
RESOLVED_STATUSES = ("Fixed", "Completed", "Won't Fix")
STATUSES = ("Open", "Ongoing", "Needs Info", "Fixed", "Completed", "Won't Fix", "Reopened")

# The status a log is allowed to start life in. Everything else has to be reached
# through a transition, so a log cannot be filed as already Completed.
INITIAL_STATUSES = ("Open", "Reopened")

# Statuses a tester verifies rather than a developer resolves — reaching one stamps
# verified_by/verified_on.
VERIFIED_STATUSES = ("Completed",)

STATUS_TRANSITIONS = {
	"Open": ("Ongoing", "Needs Info", "Won't Fix"),
	"Reopened": ("Ongoing", "Needs Info", "Won't Fix"),
	"Ongoing": ("Fixed", "Needs Info", "Won't Fix"),
	"Needs Info": ("Open", "Ongoing", "Won't Fix"),
	"Fixed": ("Completed", "Reopened"),
	"Completed": ("Reopened",),
	"Won't Fix": ("Reopened",),
}

STATUS_COLORS = {
	"Open": "red",
	"Reopened": "orange",
	"Ongoing": "blue",
	"Needs Info": "yellow",
	"Fixed": "purple",
	"Completed": "green",
	"Won't Fix": "gray",
}

# Which Test Run counter each Test Log status rolls up into.
RUN_COUNT_FIELDS = {
	"Open": "open_count",
	"Reopened": "open_count",
	"Ongoing": "ongoing_count",
	"Needs Info": "needs_info_count",
	"Fixed": "fixed_count",
	"Completed": "completed_count",
	"Won't Fix": "wont_fix_count",
}

# A run cannot be signed off while any of its logs are still in one of these.
UNSETTLED_STATUSES = ("Open", "Reopened", "Ongoing", "Needs Info")

SEVERITIES = ("Low", "Medium", "High", "Critical")
URGENT_SEVERITIES = ("High", "Critical")

TEST_TYPES = (
	"Functional",
	"UI / UX",
	"Regression",
	"Performance",
	"Security",
	"Integration",
	"Other",
)

ATTACHMENT_TYPES = ("Screenshot", "Screen Recording", "Log File", "Document", "External Link")

IMAGE_EXTENSIONS = ("png", "jpg", "jpeg", "gif", "webp", "bmp", "svg", "avif")
VIDEO_EXTENSIONS = ("mp4", "webm", "mov", "m4v", "ogv")

# Fields the list view is allowed to set on many logs at once. Anything that moves
# status goes through set_status instead, so the flow rules still apply.
BULK_EDITABLE_FIELDS = ("assigned_developer", "test_run", "severity", "target_date", "test_type")


def vocabulary() -> dict:
	"""The lists the widget needs to render its pickers, in one payload."""
	return {
		"statuses": list(STATUSES),
		"status_colors": dict(STATUS_COLORS),
		"status_transitions": {k: list(v) for k, v in STATUS_TRANSITIONS.items()},
		"initial_statuses": list(INITIAL_STATUSES),
		"severities": list(SEVERITIES),
		"test_types": list(TEST_TYPES),
	}


def can_transition(from_status: str | None, to_status: str) -> bool:
	"""Whether a log may move between these two statuses.

	A log with no previous status is being created, so only the initial statuses are
	open to it. Staying put is always allowed — most saves do not touch the status.
	"""
	if not from_status:
		return to_status in INITIAL_STATUSES

	if from_status == to_status:
		return True

	return to_status in STATUS_TRANSITIONS.get(from_status, ())


def attachment_type_for(file_name: str, mime: str | None = None) -> str:
	"""Best guess at a Test Log Attachment type from what the browser handed us."""
	mime = (mime or "").lower()
	if mime.startswith("image/"):
		return "Screenshot"
	if mime.startswith("video/"):
		return "Screen Recording"

	extension = (file_name or "").rsplit(".", 1)[-1].lower()
	if extension in IMAGE_EXTENSIONS:
		return "Screenshot"
	if extension in VIDEO_EXTENSIONS:
		return "Screen Recording"
	if extension in ("log", "txt", "json", "har"):
		return "Log File"

	return "Document"
