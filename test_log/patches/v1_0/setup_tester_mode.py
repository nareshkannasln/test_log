# Copyright (c) 2026, Aerele and contributors
# For license information, please see license.txt

"""Seed Test Log Settings on sites that had the app before tester mode existed."""

from test_log.install import setup_tester_mode


def execute():
	setup_tester_mode()
