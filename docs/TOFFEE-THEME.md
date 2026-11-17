# Toffee theme and typography

The app uses the palette proposed in issue #15: cream canvas, white surfaces,
espresso text, toffee actions, and a soft toffee-tinted sidebar (#F5EBE1).
The navigation tint separates it from the cream canvas on desktop and mobile.
The user's visual reference
sets the direction: soft rounded cards, restrained brown accents, and a compact
mobile bar with a central add action. Sage indicates success;
warning, overdue, and destructive states retain distinct colors and text labels.

DM Sans provides a softer match for the warm palette while keeping dates,
amounts, and form labels readable. The variable font supports the existing
weights without downloading multiple font files. It is served by the NAS;
there are no Google Fonts requests or other font services at runtime.

- Font source: [Google Fonts / DM Sans](https://github.com/google/fonts/tree/main/ofl/dmsans).
- Font license: [SIL Open Font License](../static/fonts/OFL.txt), included with the font.
- Shared tokens and font declaration: `static/fonts.css`.
- The family app, confirmations, and NAS guide consume shared tokens.
- The main family app defaults to light cream, with an optional light/dark
  toggle whose device-local preference works offline. Account/guide screens
  follow the device preference. Django administration retains its original
  colors, fonts, and theme selector; it does not load family theme assets.
- Browser chrome follows the chosen app theme; installed app icons use toffee
  and cream. Installers may cache their icon or initial splash color until the
  app is reinstalled; the manifest supplies the light launch background.

White labels are used on light-mode toffee buttons. Dark-mode caramel buttons
use espresso labels. Small links use the darker toffee token, and essential
input borders use a stronger color than decorative oat dividers. Placeholders
use the secondary text color. Keyboard focus stays visible on both palettes.

`tests/browser-theme.cjs`, invoked by the Django browser suite, checks rendered
text contrast, theme switching, keyboard focus, 390/768px layouts, original admin and NAS
guide styles, absence of remote requests, and the font loading after an offline
reload. Screenshots use fictional records and are saved as CI artifacts.
These checks cover representative controls and text; they are not a complete
accessibility certification.

The public service-worker cache advances to v14 and includes the font, so an
existing installation fetches the updated shell when connected. Saving financial
records for offline review remains an explicit per-device choice. No database
migrations or additional production dependencies are needed. Existing backup
and update procedures continue to apply.
