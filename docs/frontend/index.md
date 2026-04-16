# Frontend Docs

Read this section for the review workbench, interaction design, and user-visible state.

## Files

- `design-language.md`
  - Visual design principles, color tokens, tile layout rules, background animation, and typography
- `annotation-review-workbench.md`
  - Current UX for span selection, paragraph-row comment layout, exports, and run visibility

## Intake form

The workbench intake form is intentionally minimal:

- No "Draft title" input — the title is derived automatically at submission time from the first `# Heading` in the content, or from the first non-empty line (truncated to 80 characters). For URL imports the page title is used. The `title` field remains in `ReviewFormState` to support session restore and artifact hydration.
- No workspace mode selector — the persistence mode is fixed at `"workspace"`. The `persistenceMode` field remains in `ReviewFormState`.
- No debug trace toggle — debug trace is always enabled. The `includeDebugTrace` field remains in `ReviewFormState`.
- A "Choose content" label appears above a source type dropdown with four options: Pasted text, URL, Text file, Import artifact. The dropdown is hidden once content has loaded, and pasted-text runs remove the textarea once the review shell takes over.
- Pasted-text intake shows a `Preview` action before analysis starts so the reviewer can inspect the full text without leaving the intake shell.
- Text-file intake shows an explicit `Preview` action before analysis starts so `.txt` and `.md` uploads can be inspected in the same intake preview shell used for URL imports.
- "Import artifact" is one of the source type options, not a standalone button. Selecting it shows a JSON file picker inline in the source composer area.
- Artifact import is a first-class intake path for reopening a previously exported review state without rerunning analysis.
