# License and provenance notice

This publication is distributed under **GNU GPL version 3 only**, SPDX identifier
`GPL-3.0-only`. The complete license text is in `LICENSE`. The license's own Free Software
Foundation notice is retained unchanged. Project contributions remain with their
respective authors/rightsholders; no exclusive authorship claim is made here.

## Development history

The development workflow began by evaluating:

- Project: `tuliosousapro/Instagram-Close-Friends-BOT`
- Repository: https://github.com/tuliosousapro/Instagram-Close-Friends-BOT
- Reviewed branch: `feature/basic-configs`
- License reviewed: GNU General Public License version 3
- License source: https://github.com/tuliosousapro/Instagram-Close-Friends-BOT/blob/feature/basic-configs/LICENSE

The code packaged here is a refinement of the subsequently supplied local, no-reload
Playwright helper. It is not a vendored copy of the upstream instagrapi client, and does
not include its session file, credentials, configuration, or dependency stack. The GPLv3
publication choice retains conservative license continuity with the project's ancestry.
Do not remove applicable notices or relicense inherited third-party material without
reviewing its terms.

## Modifications in this distribution

The supplied no-reload helper was modified for this initial beta publication: generic
account configuration, separate private workspaces, strict input validation, history
binding, improved DOM row discovery, stricter browser endpoints, broader offline tests,
publication safeguards and documentation. The earlier development version labels are not
a history of public releases for this repository.

Python dependencies are installed separately and retain their own licenses. This notice
does not relicense Playwright, Chrome, Python, Instagram content or any other third-party
work. No endorsement by the original project author, Meta, Instagram or Playwright is
implied. No Instagram or third-party brand assets are shipped.
