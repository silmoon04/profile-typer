# Interface

The app uses a warm paper background, dark text and borders, and a lime accent
for the selected view. Field highlight colors remain controlled by the input JSON.
Type actions are dark buttons; Copy actions are outlined. Status always has
a text label, so color is not the only signal.

Space Grotesk handles headings, controls, and answer text. Space Mono handles
positions and counters. Both fonts ship with the app and their OFL notices.
The icon is a drawn T key, with matching SVG, PNG, and Windows ICO files.

The visual references were the restrained layouts in these Dribbble examples:

- [Brutalism Dashboard UI Data Visualisation](https://dribbble.com/shots/12770179-Brutalism-Dashboard-UI-Data-Visualisation)
- [Neo-brutalism UI kit for web and mobile apps](https://dribbble.com/shots/27208344-Neo-brutalism-UI-kit-for-web-and-mobile-apps)
- [To-do list and task overview](https://dribbble.com/shots/22974248-To-do-list-and-task-overview-designed-with-Bruddle-UI-kit)

The references informed typography, borders, and hierarchy. Their artwork is
not included in the app.

## Interaction rules

- Workspace stays in the same position when switching between wide and narrow
  layouts. The view list moves to its own tab when space is limited.
- Recent views keep their editor cursor, selection, undo history, and scroll
  position. The cache holds four inactive views; answer edits always live in
  the document, independently of that cache.
- Copy feedback does not change button width. Counts remain cumulative.
- Each card has one header row for its wrapping title and counted Copy/Type
  buttons. Short choices sit side by side. Single-choice fields omit the count
  line. Cards highlight on hover or focus and do not have colored edge strips.
- Click an option label to choose it, or drag across its text to select and copy.
- Save updates the open file. Save as, under More, chooses another path.
- Add remains visible. Duplicate, reorder, and remove live under Organize.
- Short windows use tighter spacing. Rows use the viewport width when deciding
  their column count, so an old wide layout cannot force horizontal overflow.
- Controls belong to their parent before becoming visible. The startup test
  watches actual top-level show events through import, navigation, and resizing.

Typography and palette live in `qt_typer/theme.py` and `assets/theme.qss`.
Document and typing rules remain independent of the visual styling.
