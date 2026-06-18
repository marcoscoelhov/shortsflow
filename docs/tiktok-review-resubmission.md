# TikTok Developer Review Resubmission

## Recovered Context From The First Demo

The original TikTok review video is `app/static/demo-videos/tiktok-developer-review-demo.mp4`.

It was created on 2026-05-22, runs for 68.2 seconds, and is a 1280x720 MP4. The video presents a sandbox/mockup review flow for the TikTok Content Posting API, not a live public production post.

The first demo showed:

1. `YTS Render Content Posting API` as the product name.
2. Requested scope `video.publish`.
3. Sandbox privacy `SELF_ONLY`.
4. Explicitly unused scopes: Share Kit, Display API, Login Kit.
5. Public website URL and redirect URL prefix verification.
6. The private Hub dashboard with TikTok cross-posting status.
7. Hub settings for TikTok publishing.
8. An approved video ready for publishing.
9. End-to-end publishing steps: approve, schedule, queue TikTok publication, track status.
10. A final checklist stating no tokens or secrets are shown.

That context is useful, but it now conflicts with the reviewer feedback because the public website and app icon were still too minimal and the visible brand was inconsistent.

## Reviewer Feedback Mapped To Corrections

### App icon

Use the same ShortsFlow icon everywhere:

- TikTok Developers Basic Info app icon: `docs/shortsflow-mark-1024.png`
- Public website favicon: `docs/shortsflow-mark-1024.png`
- Public website visible logo: `docs/shortsflow-mark-1024.png`
- Private Hub favicon and topbar logo: `app/static/shortsflow-mark-1024.png`

Do not submit a different YTS Render icon in TikTok Developers. The reviewer explicitly checks that the Basic Info icon, website logo, and browser tab favicon match.

### Website URL

Use the public URL that serves `docs/index.html`.

The website now includes:

- product identity: ShortsFlow
- TikTok publishing workflow summary
- embedded TikTok review demo
- interactive sandbox/mockup app demo
- end-to-end TikTok integration flow
- data usage explanation
- Terms of Service
- Privacy Policy
- OAuth redirect page link

Before resubmitting, open the exact Website URL in an incognito browser and confirm the ShortsFlow icon appears in the page and browser tab.

### Redirect domain

Use the exact domain that hosts the public website. The redirect domain should be only the host, not the full callback path.

Example shape:

- Website URL: `https://example.com/`
- Redirect domain: `example.com`
- Redirect URI/callback page: `https://example.com/tiktok-callback.html`

If the site is hosted under GitHub Pages, use the GitHub Pages host as the redirect domain. If a custom domain is used, use the custom domain consistently for Website URL, Redirect domain, and callback URL.

### Demo video

Do not reuse the old demo without context, because it says `YTS Render` and shows the old minimal website.

The resubmission should use one of these options:

1. Preferred: record a new demo from the updated website and Hub with ShortsFlow branding.
2. Acceptable if time is short: submit the existing MP4 with the updated demo page and a reviewer note explaining it is a sandbox/mockup end-to-end flow.

The new or explained demo must show:

- the public ShortsFlow website with the same icon
- the interactive mockup page at `docs/tiktok-integration-demo.html`
- TikTok OAuth context or callback page
- Hub settings with TikTok publishing enabled
- an approved video package
- TikTok publication queued from the approved/scheduled job
- Content Posting API call sequence: creator info, video init/upload, status fetch
- final status stored in the Hub
- no secrets, tokens, or credentials visible

## Suggested Reviewer Note

ShortsFlow is a private creator publishing workflow powered by YTS Render. We updated the public website to be fully developed and to use the same ShortsFlow icon consistently across the TikTok app icon, website logo, and favicon. The redirect domain now matches the public website domain, and the callback page is hosted on the same domain.

The demo video is a sandbox/mockup demonstration of the complete TikTok Content Posting API flow. It shows the authorized publishing context, approved video package, TikTok publication queue, upload request, status tracking, and final operational state. No production secrets, access tokens, or private credentials are displayed.

## Resubmission Checklist

- Upload `docs/shortsflow-mark-1024.png` as the TikTok app icon.
- Set Website URL to the public URL serving `docs/index.html`.
- Set Redirect domain to the same host as Website URL.
- Confirm `tiktokQZ82W1qR5IDvPKFFY9y6ib3DDh84DuoC.txt` is still publicly reachable if TikTok requires site verification.
- Use `docs/demo-videos/tiktok-developer-review-demo.mp4` or a freshly recorded ShortsFlow-branded replacement as the demo video.
- Paste the suggested reviewer note, adjusted with the real public domain.
