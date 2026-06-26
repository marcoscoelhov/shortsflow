# Impeccable Critique Ignore List

- Ignore `single-font` findings on `app/templates/base.html` where the scanner only sees the Material Symbols font link. ShortsFlow intentionally uses a system sans UI stack plus a monospace label stack in `app/static/styles.css`, which matches the product-register guidance.
