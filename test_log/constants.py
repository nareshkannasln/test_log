# Copyright (c) 2026, Aerele and contributors
# For license information, please see license.txt

"""The app's shared vocabulary: statuses, how they move, and the pick lists.

The Python controllers and the browser widget both read from here — the widget gets
its copy through the boot info — so the two can never drift apart.
"""

OPEN_STATUSES = ("Open", "Reopened")
RESOLVED_STATUSES = ("Fixed", "Completed", "Won't Fix")
STATUSES = ("Open", "Ongoing", "Fixed", "Completed", "Won't Fix", "Reopened")

STATUS_TRANSITIONS = {
	"Open": ("Ongoing", "Won't Fix"),
	"Reopened": ("Ongoing", "Won't Fix"),
	"Ongoing": ("Fixed", "Won't Fix"),
	"Fixed": ("Completed", "Reopened"),
	"Completed": ("Reopened",),
	"Won't Fix": ("Reopened",),
}

STATUS_COLORS = {
	"Open": "red",
	"Reopened": "orange",
	"Ongoing": "blue",
	"Fixed": "purple",
	"Completed": "green",
	"Won't Fix": "gray",
}

# Which Test Run counter each Test Log status rolls up into.
RUN_COUNT_FIELDS = {
	"Open": "open_count",
	"Reopened": "open_count",
	"Ongoing": "ongoing_count",
	"Fixed": "fixed_count",
	"Completed": "completed_count",
	"Won't Fix": "wont_fix_count",
}

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


def vocabulary() -> dict:
	"""The lists the widget needs to render its pickers, in one payload."""
	return {
		"statuses": list(STATUSES),
		"status_colors": dict(STATUS_COLORS),
		"status_transitions": {k: list(v) for k, v in STATUS_TRANSITIONS.items()},
		"severities": list(SEVERITIES),
		"test_types": list(TEST_TYPES),
	}


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
