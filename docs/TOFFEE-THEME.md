# Toffee theme and typography

The app uses the palette proposed in issue #15: cream canvas, white surfaces,
espresso text, toffee actions, and a slate navy sidebar. Sage indicates success;
warning, overdue, and destructive states retain distinct colors and text labels.

DM Sans provides a softer match for the warm palette while keeping dates,
amounts, and form labels readable. The variable font supports the existing
weights without downloading multiple font files. It is served by the NAS;
there are no Google Fonts requests or other font services at runtime.

- Font source: [Google Fonts / DM Sans](https://github.com/google/fonts/tree/main/ofl/dmsans).
- Font license: [SIL Open Font License](../static/fonts/OFL.txt), included with the font.
- Shared tokens and font declaration: `static/fonts.css`.
- App, confirmations, NAS guide, and administration consume the same tokens.
- Dark mode follows the device preference. Django administration retains its
  own light/dark/automatic selector, using the same palette in each mode.
- Browser chrome uses light/dark theme metadata; installed app icons use slate
  and cream. Installers may cache their icon or initial splash color until the
  app is reinstalled; the manifest supplies the light launch background.

White labels are used on light-mode toffee buttons. Dark-mode caramel buttons
use espresso labels. Small links use the darker toffee token, and essential
input borders use a stronger color than decorative oat dividers. Placeholders
use the secondary text color. Keyboard focus stays visible on both palettes.

`tests/browser-theme.cjs`, invoked by the Django browser suite, checks rendered
text contrast, theme switching, keyboard focus, 390/768px layouts, admin and NAS
guide styles, absence of remote requests, and the font loading after an offline
reload. Screenshots use fictional records and are saved as CI artifacts.
These checks cover representative controls and text; they are not a complete
accessibility certification.

The public service-worker cache advances to v12 and includes the font, so an
existing installation fetches the updated shell when connected. Saving financial
records for offline review remains an explicit per-device choice. No database
migrations or additional production dependencies are needed. Existing backup
and update procedures continue to apply.
