# Design QA — 24 October 2026

**Final result:** passed

**Source visual truth**
- Selected option 2: `/Users/vguillet/.codex/generated_images/01a16a71-5dc8-77b2-846a-a852f75a9e27/exec-9be7c3bc-365f-4034-aff9-63929ce8ba38.png`.
- User’s later layout reference (takes precedence for the action strip): `/Users/vguillet/.codex/.chatgpt-projects/g-p-697effec50fc8191bf4d72dc8d4e8afc/outputs/auto-secretaire-upgrade-2026-10-24/source-controls-layout.png`.
- Subsequent explicit overrides: title uses full available width, icons align with status badges, destination stays below, remove auto/grouped control and explanatory text, show actionable printing badges.

**Implementation evidence**
- Local app tested at http://127.0.0.1:8883/. Full workspace: `/Users/vguillet/.codex/.chatgpt-projects/g-p-697effec50fc8191bf4d72dc8d4e8afc/outputs/auto-secretaire-upgrade-2026-10-24/12-final-workspace.png`.
- Full detail crop: `/Users/vguillet/.codex/.chatgpt-projects/g-p-697effec50fc8191bf4d72dc8d4e8afc/outputs/auto-secretaire-upgrade-2026-10-24/14-final-mail-detail.png`.
- Source and implementation focused comparison: `/Users/vguillet/.codex/.chatgpt-projects/g-p-697effec50fc8191bf4d72dc8d4e8afc/outputs/auto-secretaire-upgrade-2026-10-24/15-controls-comparison.png`.
- Compact controls: `/Users/vguillet/.codex/.chatgpt-projects/g-p-697effec50fc8191bf4d72dc8d4e8afc/outputs/auto-secretaire-upgrade-2026-10-24/13-narrow-controls.png`. Desktop capture: `/Users/vguillet/.codex/.chatgpt-projects/g-p-697effec50fc8191bf4d72dc8d4e8afc/outputs/auto-secretaire-upgrade-2026-10-24/10-desktop-final.png`.
- Source and implementation pixel dimensions: {'exec-9be7c3bc-365f-4034-aff9-63929ce8ba38.png': (1096, 1435), 'source-controls-layout.png': (1106, 286), '12-final-workspace.png': (545, 1510), '14-final-mail-detail.png': (335, 662), '13-narrow-controls.png': (378, 818)}.
- Actual CSS viewports measured in DOM: 1280×720, 720×634, 390×844. Browser reports DPR 2.6 with its existing zoom. IAB full-page exports are downsampled (545 px wide for the 720 px CSS view); compare relative card widths, not raw pixel distances. Focused comparison normalizes both card regions to 600 px width. The first 390 px full-page export clipped the right edge during capture; the normal browser capture 13-narrow-controls.png replaces it as visual evidence. DOM confirms controls fit and there is no horizontal overflow. Temporary viewport override reset.
- State: fictitious Camille Moreau email, expanded body, classified PDF and attachment; final PDF print simulated, attachment pending. Reference content/date/destination differ, so copy and badge state are compared by function, not exact message text.

**Comparison history and findings**
1. Initial build (06-email-footer-initial.png): [P2] legacy arrow/Finder glyphs did not match the selected concept’s coherent outline icons; the action strip did not match the user’s clarified placement. Fixed with unmodified local Lucide eye/folder/printer assets and a status/actions row above a full-width destination.
2. Intermediate build: [P2] attachment filename shared its horizontal space with action buttons, forcing an avoidable wrap. Fixed by putting the title above a separate status/actions row.
3. Final comparison: selected concept and final full-detail crop opened together; latest user reference and implemented attachment combined in 15-controls-comparison.png. No remaining actionable P0/P1/P2 differences against the final user instructions. Later removals and terminology changes are intentional overrides, not drift.

**Required fidelity surfaces**
- Typography: existing Inter/system stack, dark green title at 18 px, document names at 13 px and badges at 11 px retained. Full-width name has the same measured width as its information container. Long names wrap without obscuring actions. Source is a larger isolated mock; existing app density is intentionally preserved.
- Spacing/layout: white email surface and attached pale sage footer; metadata before body; distinct attachment section. Icons sit to the right of the status row, destination spans the full width below. Narrow badges may wrap within their own left-hand group while controls remain visible. Subject/body disclosure and undo remain existing product functions absent from the mock.
- Colors/tokens: existing forest ink, sage footer, amber pending and blue simulated states retained. No false green success for a simulation.
- Assets: three licensed Lucide SVGs, unmodified, rendered as current-color masks at 22 px within 36 px controls; sharp in normal browser capture, consistent stroke weight. No generated art or handcrafted icon substitutes. Enlarged full-page evidence is softer because IAB downsamples that export, not because the icons are rasterized.
- Copy: obsolete PDF label and auto/grouped explanation/control removed. Pending, printer submission, simulation and errors are explicit; no ambiguous “Envoyés”. Dynamic test names and paths remain real demo data.

**Interaction checks**
PDF-only filing and undo, inline search, one simulated print leaving attachment untouched, cancelled reprint confirmation, collapsed/expanded body, zero-attachment state, matching document IDs and accessible icon names. Final badge helper: 9 added automated scenarios; 43 targeted tests pass. Browser error log empty. No physical printing or Finder launch claimed.

**Open questions / residual limits**
No blocking visual questions. Physical printer and Apple Mail integration remain outside this presentation change.

**Implementation checklist**
- [x] Unify email/PDF and separate attachments.
- [x] Apply final name/status/actions/destination hierarchy.
- [x] Bundle matching icons and licence, verify wheel contents.
- [x] Apply badge and copy corrections without changing stored choices.
- [x] Check responsive controls, interactions, tests and console.

final result: passed

**Main app handoff:** http://127.0.0.1:8765/ refreshed and verified after fast-forward. Main screenshot: `/Users/vguillet/.codex/.chatgpt-projects/g-p-697effec50fc8191bf4d72dc8d4e8afc/outputs/auto-secretaire-upgrade-2026-10-24/16-main-app-final.png`. No document or stored preference changes during deployment.
