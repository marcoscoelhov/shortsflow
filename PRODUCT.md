# Product

## Register

product

## Users

ShortsFlow is used by a solo operator or small channel team producing YouTube Shorts in pt-BR. The operator is usually in an execution loop: create jobs, watch output, approve or reject, schedule publication, check automation state, inspect failures, and keep the channel moving without reading terminal logs.

Secondary users are technical maintainers using the Hub de Revisao to validate provider routing, artifacts, OAuth state, publication schedules, and pipeline health. They need high-signal operational evidence without exposing secrets or turning the product into a debugging cockpit.

## Product Purpose

ShortsFlow turns editorial ideas, ready scripts, automatic topics, media generation, review, scheduling, and publication into one operational workflow for Shorts. Success means a person can see what needs action now, understand why a job is blocked or ready, and trust the hub as the source of truth for review and publication state.

The product is not a marketing website. It is a work surface for repeated decisions under real production constraints: provider latency, factual quality, monetization readiness, YouTube scheduling, local artifacts, and automation attempts.

## Brand Personality

Calm, operational, exact.

The voice should feel like a senior production console: compact, factual, and action-oriented. It should reduce anxiety when jobs are running or blocked, separate technical success from publish readiness, and make the next action obvious.

## Anti-references

- Do not make the Hub de Revisao feel like a landing page, sales dashboard, or decorative SaaS homepage.
- Do not use oversized hero sections, generic metric cards, ornamental gradients, glassmorphism, or purple-blue AI-tool styling.
- Do not hide daily controls behind vague admin language.
- Do not expose internal slugs, provider noise, stack traces, secrets, or raw implementation details as primary UI copy.
- Do not use modals as the first solution for every control; use them only for focused interruption or compact global tools that would otherwise dominate the work surface.

## Design Principles

1. Decision first: every screen should answer what needs attention, what is safe, and what action comes next.
2. Evidence without noise: technical artifacts and diagnostics should be available, but secondary to watch, approve, schedule, and publish.
3. Portuguese for operators: visible UI labels should use pt-BR product language, not internal slugs or English implementation names.
4. Dense, not cramped: repeated work should be scannable and efficient, with stable row layouts, compact badges, and predictable filters.
5. Automation stays legible: automatic jobs must show Origem do Job, Via de Criacao do Job, eligibility, schedule state, and failure reasons clearly enough to trust or override.

## Accessibility & Inclusion

Target WCAG AA for text contrast, focus visibility, keyboard access, form labels, and status announcements. The hub should work at mobile and desktop sizes, preserve state during refreshes, and avoid relying on color alone for status. Motion should be short, state-driven, and safe for reduced-motion users.
