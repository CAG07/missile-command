# Font Assets

Font assets for Missile Command text rendering.

## Files

- **PressStart2P-Regular.ttf** — Arcade-style pixel font used for scores, wave numbers, and HUD text
- **OFL.txt** — SIL Open Font License for PressStart2P

## Font Rendering Notes

- Original arcade uses orientation-aware bitmap renderer (8×8 glyphs)
- Same renderer used for font glyphs and city graphics
- Cocktail mode requires horizontal flipping capability
- Scrolling text uses background colors 0 and 1

## Fallback

If custom bitmap font is unavailable, pygame's default font is used as fallback.
Monospace is required for consistent number alignment at 256×231 resolution.
