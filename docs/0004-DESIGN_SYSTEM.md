# Vinosports Design System

> Living reference for colors, typography, and component patterns across all vinosports league apps.

## Brand Direction

**Premium / luxe** — Wine-inspired tones, warm neutrals, gold accents. The name "vinosports" bridges wine culture and sports betting, and the visual identity should feel like a high-end members' lounge rather than a neon-lit sportsbook.

**Default theme: Light mode.** Dark mode is supported as an alternate.

---

## Color Palette

### Foundation (shared across all leagues)

| Token               | Light Mode   | Dark Mode    | Usage                                |
|---------------------|-------------|-------------|--------------------------------------|
| `--color-bg`        | `#FAFAF8`   | `#0C0A09`   | Page background                      |
| `--color-surface`   | `#FFFFFF`   | `#1C1917`   | Card/panel backgrounds               |
| `--color-dark`      | `#1C1917`   | `#0C0A09`   | Navbar, inverse surfaces             |
| `--color-text`      | `#1C1917`   | `#FAFAF5`   | Primary text                         |
| `--color-muted`     | `#78716C`   | `#A8A29E`   | Secondary/muted text                 |
| `--color-border`    | `#E7E5E4`   | `#292524`   | Card borders, dividers               |
| `--color-gold`      | `#B8860B`   | `#D4A843`   | Brand accent (vinosports wordmark)   |

### Semantic Colors

| Token       | Value       | Usage                           |
|-------------|-------------|----------------------------------|
| `danger`    | `#DC2626`   | Errors, relegation, losses       |
| `warning`   | `#D97706`   | Caution states                   |
| `positive`  | `#16A34A`   | Profit, wins, positive streaks   |

### Per-League Accent Colors

Each league app swaps the `--color-accent` variable to create its own identity while sharing the same layout and component patterns.

| League | Accent          | Accent Nav       | Accent Light    | League Color       |
|--------|----------------|------------------|-----------------|---------------------|
| EPL    | `#4A2040` plum  | `#8B4A6B` wine   | `#F5EDF2`       | `#3D1152` purple    |
| NBA    | `#C2410C` burnt orange | TBD       | `#FFF7ED`       | `#1D4ED8` blue     |

**Accent usage:** Primary buttons, odds buttons, highlighted data, focus rings, links on light surfaces.

**Accent nav usage:** Logo text, active nav link — readable on the always-dark navbar. In dark mode this typically matches accent since accent is already light enough.

**Accent light usage:** Card hover backgrounds, active tab backgrounds, selected row tinting.

---

## Typography

| Role        | Font         | Weights     | Notes                                      |
|-------------|-------------|-------------|---------------------------------------------|
| Body        | Inter        | 400, 500    | Clean readability for all body text          |
| Headings    | Oswald       | 500, 600    | Bold sports character; uppercase for section headers |
| Monospace   | Roboto Mono  | 400, 700    | Odds, balances, numeric data                 |
| Logo        | Oswald       | 700         | `letter-spacing: 0.05em`, uppercase          |

**Hierarchy:**
- Page titles: Oswald 600, 1.875rem (30px)
- Section headers: Oswald 500, uppercase, tracking-wider
- Card headers: Inter 600, 0.875rem (14px)
- Body: Inter 400, 0.875rem (14px)
- Small/caption: Inter 400, 0.75rem (12px)

---

## Component Patterns

### Cards (fixture cards, standings, leaderboard panels)
- Background: `bg-surface`
- Border: `border border-[var(--color-border)]`
- Border radius: `rounded-xl` (12px)
- Shadow: `shadow-sm` (subtle depth in light mode)
- Hover: border shifts toward accent, background tints with accent-light
- Padding: `p-4` standard, `p-5` for sidebar panels

### Navbar
- Always dark (`bg-dark`) in both light and dark themes for premium feel
- Logo text in accent color
- Nav links: `text-stone-400` default, `text-white` on hover, accent color when active
- User balance displayed in accent + mono font

### Tables (standings, leaderboard, odds)
- Header row: uppercase, tracking-wider, muted text, border-bottom
- Row hover: light accent-tint background
- Current-user row: accent/5 background tint
- Borders: `border-[var(--color-border)]` between rows

### Odds Buttons
- Background: surface or slight dark tint
- Text: accent color, mono font, bold
- Hover: accent/10 background
- Disabled/locked: muted text, no hover effect

### Tabs (matchday selector, leaderboard type)
- Container: subtle background (`bg-surface` or `bg-dark/5`)
- Active tab: accent background tint + accent text
- Inactive: muted text, hover to white/primary

### Status Badges
- Scheduled: muted outline
- Live/In Play: pulsing accent dot + accent text
- Finished: muted, no emphasis

---

## Theme Switching

The theme system uses `data-theme` attribute on `<body>` with CSS custom properties. All theme-dependent colors flow through CSS variables so templates use semantic Tailwind classes (`bg-surface`, `text-accent`, `text-muted`, `border-subtle`) rather than hardcoded color values.

**Light mode** is the default. Dark mode inverts the foundation colors while keeping accent/semantic colors consistent.

---

## Per-League Differentiation

Beyond accent color, each league can have:
- **League-colored header accents** — a thin top-border or gradient on the navbar using `--color-epl` / `--color-nba`
- **League logo + wordmark** in the navbar
- **Card hover tint** using the league's accent-light color

The layout, typography, component shapes, and interaction patterns remain identical across leagues.
