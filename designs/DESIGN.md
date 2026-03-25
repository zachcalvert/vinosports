# Design System Document: The Mid-Century Mainstay

## 1. Overview & Creative North Star
The Creative North Star for this design system is **"The Mid-Century Mainstay."** This system rejects the sterile, frictionless aesthetic of modern SaaS in favor of the tactile, sun-faded nostalgia of 1970s American athletics. It is the digital equivalent of a well-worn varsity jacket, a scuffed hardwood court, and the mechanical hum of a boardwalk jukebox.

To move beyond a "templated" look, this system utilizes **Intentional Asymmetry** and **Tonal Layering**. We avoid rigid, centered grids in favor of layouts that feel "posted" or "pinned," mirroring the organic feel of a locker room bulletin board. We break the digital fourth wall by using overlapping elements—where typography or imagery spills across container boundaries—to create depth and a sense of physical assembly.

## 2. Colors & Surface Philosophy
The palette is rooted in a "Sun-Faded" reality. Every color must feel like it has lived under the Coney Island sun.

### Palette Strategy
- **Primary (#b3262f):** Our "Sport Red." Used for high-energy actions and brand presence.
- **Secondary (#485f84):** "Heritage Navy." Provides the grounding, "official" tone of a sports league.
- **Tertiary (#765a05):** "Boardwalk Gold." Reserved for "MVP" moments—highlights, trophies, and premium callouts.
- **Surface (#f3fcf0):** "Parchment." The foundation of the system. Never use pure white (#FFFFFF) for backgrounds; the warmth of the parchment is what gives the system its analog soul.

### The "No-Line" Rule
Traditional 1px solid borders are strictly prohibited for sectioning. They are the hallmark of cheap, generic UI. Instead:
- **Background Shifts:** Define sections by transitioning from `surface` to `surface-container-low`.
- **Athletic Stripes:** Use the Spacing Scale (e.g., `spacing-1` or `spacing-2`) to create thick, 2-4px "Varsity Stripes" using the `outline-variant` or `primary` color to separate major content blocks.

### Surface Hierarchy & Nesting
Treat the UI as a series of stacked physical materials. 
- Use `surface-container-lowest` for the most "elevated" cards.
- Place them on a `surface-container` section.
- This creates a soft, nested depth that feels like layers of cardstock rather than digital pixels.

### The "Glass & Gradient" Rule
To mimic the plastic sheen of a 70s jukebox, use subtle gradients on primary CTAs (transitioning from `primary` to `primary-container`). For floating navigation or overlays, use **Glassmorphism**: semi-transparent `surface` colors with a `backdrop-blur` of 12px-20px, allowing the underlying "team colors" to bleed through softly.

## 3. Typography
Our typography is a dialogue between the "Athletic Hero" and the "Technical Statistician."

- **Display & Headlines (Epilogue):** A bold, chunky sans-serif that mimics vintage collegiate lettering. It should be tracked slightly tighter (`-2%` to `-4%`) to feel like a heavy-duty print.
- **Body & Labels (Public Sans):** A high-legibility workhorse. While the headlines provide the "vibe," the body text provides the "data." 

**Hierarchy Tone:** Use `display-lg` for impactful, editorial statements. Use `label-md` in all-caps with increased letter spacing (`+5%`) for a "vintage ticket stub" feel.

## 4. Elevation & Depth
In this system, depth is earned, not added. We move away from the "shadow-heavy" look of Material Design toward **Tonal Layering.**

- **The Layering Principle:** Depth is achieved by stacking `surface-container` tiers. An "Inner Card" should always be one tier higher (`surface-container-lowest`) than its parent (`surface-container-low`).
- **Ambient Shadows:** Shadows are rare. When used, they must be ultra-diffused: `blur: 24px`, `opacity: 6%`, and tinted with the `secondary` (Navy) color rather than black. This mimics natural light in a gymnasium.
- **The Ghost Border:** For high-density data, use the `outline-variant` token at **15% opacity**. It should be felt, not seen.
- **Tactile Textures:** Apply a subtle grain overlay (SVG noise at 2-3% opacity) across the entire `background` to eliminate the "flatness" of the screen.

## 5. Components

### Buttons
- **Primary:** Rounded (`rounded-full`), `primary` background, with a `primary-fixed-dim` 2px bottom-inset shadow to create a "jukebox button" feel. On hover, the button should "press" (translate Y: 1px).
- **Secondary:** `secondary` background with `on-secondary` text. No 3D effect; keep it matte.

### Cards & Lists
- **Rule:** **No Divider Lines.** 
- Separate list items using `spacing-4` vertical gaps or alternating background shifts (`surface-container-low` vs `surface-container-high`).
- **Cards:** Use `rounded-lg` or `rounded-xl`. Always use a `surface-container-lowest` background to make them "pop" against the parchment base.

### Chips
- **Selection Chips:** Should resemble vintage "I Voted" or "Hello My Name Is" stickers. Use `rounded-sm` for a slightly more angular, retro feel compared to buttons.

### Varsity Dividers (Special Component)
- Instead of a line, use a triple-stripe element: 4px `primary`, 2px `surface`, 2px `secondary`. This is the signature "Varsity Stripe" used to conclude major sections.

## 6. Do's and Don'ts

### Do:
- **Do** embrace "off" alignments. A headline that starts slightly further left than the body text creates an editorial, high-end feel.
- **Do** use `Boardwalk Gold` sparingly—only for achievement, selection, or "MVP" status.
- **Do** use thick, heavy stroke weights (2pt+) for icons to match the chunky weight of the Epilogue typeface.

### Don't:
- **Don't** use pure #000000 for text. Use `on-surface` (#161d16) to maintain the sun-faded look.
- **Don't** use 1px borders. If you feel you need one, use a background color shift instead.
- **Don't** use snappy, "modern" easing for animations. Use slightly slower, "heavier" transitions (300ms-450ms) to mimic the weight of analog machinery.

### Accessibility Note:
While we use sun-faded colors, ensure that `on-primary` and `on-secondary` text maintains a 4.5:1 contrast ratio against their respective backgrounds. The warmth of the parchment (`surface`) must never compromise the legibility of the `body-md` data.
