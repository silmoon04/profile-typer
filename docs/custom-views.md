# Custom views

A view is one step in your workflow. It can contain several text fields,
reference values, and sets of options. **Back** and **Next** move between views.
Each field has its own Copy and Type buttons, so typing one answer does not
skip the other fields in that view.

The original format still works:

```json
{"title": "hello", "description": "text to type out"}
```

For grouped fields, put views inside a `views` array:

```json
{
  "title": "My answer guide",
  "views": [
    {
      "title": "Repository",
      "color": "blue",
      "rows": [
        {
          "columns": 2,
          "fields": [
            {"title": "Task ID", "text": "example-task"},
            {
              "title": "Repository URL",
              "text": "https://example.org/project",
              "actions": ["copy"]
            }
          ]
        },
        {
          "fields": [
            {"title": "What I know about this codebase", "text": "My notes."}
          ]
        }
      ]
    }
  ]
}
```

Open the file or paste it with **Paste JSON**. A complete example with a task,
options, and an A/B rubric is in `src/profile_typer/examples/views.json`.

## Fields and rows

| Property | Meaning | Default |
| --- | --- | --- |
| View `title` | The heading and queue label. | Required |
| View `rows` | Rows in top-to-bottom order. | Required |
| Row `fields` | Fields in left-to-right order. | Required |
| Row `columns` | Maximum columns in this row, from 1 to 4. | 1 |
| Field `title` | The field label. It is not typed by the Type button. | Required |
| Field `text` | Editable answer or reference text. `description` is also accepted. | Empty string |
| Field `actions` | Which buttons to show: `copy`, `type`, both, or neither. | Both |
| View or field `color` | Card highlight color on hover or focus. | Blue, or the view's color |
| View or field `id` | Optional stable identifier. Omit it unless you need to refer to fields in another tool. | Generated |

Use a row with two fields for A/B values, then a one-column row for the
comparative rationale below them. For a rubric, a useful order is statement,
dimension/source, A/B, and evidence/reason. The JSON decides that order.

Rows collapse into fewer columns when the window is narrow. Text grows to fit
its wrapped content, and the whole view scrolls only when needed. The app does
not add a separate scrolling box inside each text field. Type and Copy are
near the top of each card, so a long answer does not hide its actions at the
bottom. The destination, Stop button, and typing settings stay outside the
scrolling view.

## Options

Single choice:

```json
{
  "title": "A",
  "options": ["YES", "NO"],
  "selected": "YES",
  "option_columns": 2
}
```

Several selected options:

```json
{
  "title": "Capabilities",
  "options": ["Code comprehension", "Testing", "Documentation"],
  "selected": ["Code comprehension", "Testing"],
  "multiple": true,
  "option_columns": 2
}
```

The app shows checked and unchecked options, with a count for multiple choices.
`selected` must use the exact option labels. `multiple` defaults to false, and
Short sets of up to three labels default to one row; other sets default to one
column. Set `option_columns` explicitly to control this. A selected string or a one-item array is valid
for a single-choice field.

Copy and Type use the selected labels, one per line, in the order of `options`.
**Custom text** lets you enter a custom value instead. A custom value
clears the option selection; choosing an option again replaces the custom text.
A custom answer can also be authored with `text` and an empty `selected` array.
Do not provide both a nonempty custom text and selected options.

Option labels remain selectable text. You can highlight part of a label and
copy that selection with Ctrl+C or the context menu. That copy is counted for
the field too.

## Colors

Use `blue`, `green`, `amber`, `red`, `purple`, `teal`, `orange`, `gray`, or a hex
color such as `#315b82`. A field color overrides its view's color. The app uses
light backgrounds and dark text so custom highlights remain readable.

If a choice has no explicit field color, YES/PASS uses green, NO/FAIL uses red,
and PARTIAL uses amber. Other choices use the view color. Colors are visual
only and never become part of copied or typed text.

## Counters and progress

- The clipboard icon counts Copy actions, including selected text copied with
  Ctrl+C or the context menu. A field's Copy button always copies its full answer.
- The pencil icon counts accepted typing starts. A cancelled countdown still
  counts as a start; **Stopped** or **Failed** distinguishes it from **Done**.
- Editing an answer after using it marks the field **Edited**. Counts remain
  cumulative so you can see how often you have used the field.
- Save JSON to preserve edits, selections, counters, and statuses. There is no
  background save of your answers. **More > Reset counters in this view** starts
  the current view's progress over. Duplicating a view also resets its counters.
- Save updates the open file. Use **More > Save as** to write another copy.
- Preview mode records preview actions. Its counts do not mean text reached
  another application.

Saved fields may include `copies`, `types`, and `status`; you do not need to
write those yourself. IDs are included when saving custom views. If you append
a file with IDs that already exist, the imported IDs are remapped so their
counters stay independent. Duplicate IDs inside one input file are rejected.

The simple title/description format remains usable by older readers. Once you
append custom views to it, saving uses the view format to preserve all fields.
Typing in custom views always stays on the current view. Auto-advance continues
to work for simple queues.

## Validation and limits

The app checks the entire import before replacing the current document.
Errors identify the affected view, row, or field. It rejects duplicate JSON
keys, unknown view-format properties, invalid colors, missing option labels,
and contradictory selections. Empty answers are valid while drafting; their
Type and Copy buttons stay disabled.

Limits are 500 views, 5,000 fields, 200 options per field, 100 rows per view,
250,000 characters per value, and 5,000,000 characters of JSON input. JSON
values are plain text. HTML, JavaScript, URLs, and shell commands are not
executed by the view renderer. File references are text or copy fields; this
feature does not upload files to another application.

## Convert an existing answer guide

The included converter supports the example answer-guide layout with an
`answer-state` JSON data block. It takes reference values and options from
that block and the latest answer prose from the title/description JSON:

```sh
python scripts/convert_answer_guide.py path/to/answer-guide.html \
  --answers path/to/answers.json --output path/to/profile-typer-views.json
```

It emits a view JSON file and a short companion `.txt` guide. It does not
execute the HTML's scripts or change the originals. It checks that all guide
fields are assigned and every supplied answer title matches. This converter
targets that answer-guide format; other workflows can author view JSON directly.
