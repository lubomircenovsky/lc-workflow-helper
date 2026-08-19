from __future__ import annotations

import json
from dataclasses import asdict

import bpy

from .models import BatchReport


REPORT_TEXT_PREFIX = "LCW_AIQ_Report_"


def report_to_dict(report: BatchReport) -> dict[str, object]:
    return asdict(report)


def write_report_text(report: BatchReport) -> bpy.types.Text:
    text_name = f"{REPORT_TEXT_PREFIX}{report.report_id}"
    text = bpy.data.texts.get(text_name) or bpy.data.texts.new(text_name)
    text.clear()
    text.write(json.dumps(report_to_dict(report), indent=2, sort_keys=True))
    return text


def write_structured_text(prefix: str, report_id: str, payload: dict[str, object]) -> bpy.types.Text:
    text_name = f"{prefix}{report_id}"
    text = bpy.data.texts.get(text_name) or bpy.data.texts.new(text_name)
    text.clear()
    text.write(json.dumps(payload, indent=2, sort_keys=True))
    return text
