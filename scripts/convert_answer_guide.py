"""Convert an answer-guide HTML data block into Profile Typer views, without executing HTML or scripts."""
from __future__ import annotations

import argparse
import json
import re
from html.parser import HTMLParser
from pathlib import Path


class StateParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = False
        self.parts = []
        self.matches = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script" and attrs.get("id") == "answer-state" and attrs.get("type") == "application/json":
            self.active = True
            self.matches += 1

    def handle_data(self, data):
        if self.active:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == "script":
            self.active = False


def convert(html: str, answers: list[dict]) -> dict:
    parser = StateParser()
    parser.feed(html)
    if parser.matches != 1:
        raise ValueError("Expected exactly one application/json script with id answer-state.")
    state = json.loads("".join(parser.parts))
    fields = {field["id"]: field for field in state["fields"]}
    if len(fields) != len(state["fields"]):
        raise ValueError("The guide contains duplicate field ids.")
    overrides = {answer["title"]: answer["description"] for answer in answers}
    if len(overrides) != len(answers):
        raise ValueError("The answer JSON contains duplicate titles.")
    unmatched = set(overrides) - {field["title"] for field in fields.values()}
    if unmatched:
        raise ValueError(f"Answer titles not found in the guide: {sorted(unmatched)}")
    used = set()
    colors = ["blue", "purple", "amber", "teal", "orange", "green", "red", "gray"]

    def field(identity, *, title=None, options=False, color=None, copy_only=False):
        original = fields[identity]
        used.add(identity)
        value = overrides.get(original["title"], original["value"])
        item = {"id": identity, "title": title or original["title"]}
        if original["kind"] == "multiselect" or options:
            labels = [str(option) for option in original["options"]]
            item.update(options=labels, selected=value if isinstance(value, list) else str(value))
            if original["kind"] == "multiselect":
                item.update(multiple=True, option_columns=2)
        else:
            item["text"] = value if isinstance(value, str) else str(value)
        if color:
            item["color"] = color
        if copy_only:
            item["actions"] = ["copy"]
        return item

    def row(*items, columns=1):
        return {"columns": columns, "fields": list(items)}

    def view(identity, title, rows, color="blue"):
        return {"id": identity, "title": title, "color": color, "rows": rows}

    views = [
        view("repository", "Repository", [
            row(field("task-id")),
            row(field("repository-url", copy_only=True), field("commit", copy_only=True), columns=2),
            row(field("codebase-source", copy_only=True), field("license", copy_only=True), columns=2),
        ]),
        view("codebase-context", "Codebase and task context", [
            row(field("repository-knowledge")),
            row(field("task-type", copy_only=True), field("task-upload", copy_only=True), columns=2),
            row(field("capabilities", copy_only=True)),
        ], "teal"),
        view("task", "Task prompt", [row(field("prompt")), row(field("realism")), row(field("quality-differences"))], "purple"),
        view("baseline-tests", "Baseline and test coverage", [row(field("baseline")), row(field("automated-tests", options=True)), row(field("test-coverage"))], "amber"),
        view("run-files", "Run files and checks", [
            row(field("job-upload", copy_only=True)),
            row(field("trial-a", copy_only=True), field("patch-a", copy_only=True), columns=2),
            row(field("trial-b", copy_only=True), field("patch-b", copy_only=True), columns=2),
            row(field("verification", copy_only=True)),
        ], "gray"),
        view("correctness", "Correctness", [
            row(field("correctness-a", title="A", options=True), field("correctness-b", title="B", options=True), columns=2),
            row(field("correctness-reason")),
        ], "green"),
    ]
    dimension_ids = sorted(int(match.group(1)) for identity in fields if (match := re.fullmatch(r"dimension-(\d+)-reason", identity)))
    for number in dimension_ids:
        prefix = f"dimension-{number}"
        title = fields[prefix + "-reason"]["title"].removesuffix(": Comparative Rationale")
        views.append(view(prefix, title, [
            row(field(prefix + "-a", title="A rating"), field(prefix + "-b", title="B rating"), columns=2),
            row(field(prefix + "-reason", title="Comparative rationale")),
        ], colors[(number - 1) % len(colors)]))
    rubric_ids = sorted(int(match.group(1)) for identity in fields if (match := re.fullmatch(r"rubric-(\d+)-statement", identity)))
    for number in rubric_ids:
        prefix = f"rubric-{number}"
        dimension = int(fields[prefix + "-dimension"]["value"])
        views.append(view(prefix, f"Rubric {number}", [
            row(field(prefix + "-statement", title="Statement")),
            row(field(prefix + "-dimension", title="Dimension", copy_only=True), field(prefix + "-source", title="Source", copy_only=True), columns=2),
            row(field(prefix + "-a", title="A", options=True), field(prefix + "-b", title="B", options=True), columns=2),
            row(field(prefix + "-reason", title="Evidence and reason")),
        ], colors[(dimension - 1) % len(colors)]))
    views.extend([
        view("comparison", "Overall comparison", [
            row(field("quality-a", title="A quality"), field("quality-b", title="B quality"), columns=2),
            row(field("preference", copy_only=True)), row(field("preference-reason")), row(field("optional-comments")),
        ], "teal"),
        view("report", "Evaluation report", [row(field("evaluation-report", copy_only=True))], "gray"),
    ])
    if used != set(fields):
        raise ValueError(f"Guide fields were not assigned to views: {sorted(set(fields) - used)}")
    return {"schema_version": 1, "title": state["title"], "views": views}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("html", type=Path)
    parser.add_argument("--answers", type=Path, required=True, help="latest title/description answer JSON")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from profile_typer.view_schema import parse_views
    result = convert(args.html.read_text(encoding="utf-8-sig"), json.loads(args.answers.read_text(encoding="utf-8-sig")))
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    parsed = parse_views(text)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8", newline="\n")
    notes = ["Profile Typer custom views", "", "Open the JSON file in Profile Typer 0.3.0 or later.",
             "Each view groups related answers and reference fields. Back and Next move between views.",
             "Copy and Type act on one field. Counters record copy actions and typing starts; statuses show outcomes.",
             "Save JSON preserves edits, selections, and counters. Your original files were not changed.", "", "Views:"]
    notes.extend(f"{index}. {entry.title} ({len(entry.fields)} fields)" for index, entry in enumerate(parsed.entries, 1))
    args.output.with_suffix(".txt").write_text("\n".join(notes) + "\n", encoding="utf-8", newline="\n")
    print(f"Converted {len(parsed.entries)} views and {sum(len(entry.fields) for entry in parsed.entries)} fields.")


if __name__ == "__main__":
    main()
