# Profile cards

`render_cards.py` is the single implementation script. It reads `data/contributions.json`, subsets the bundled fonts with FontTools' `pyftsubset` implementation, and generates `cards/`, `README.md`, and a local `preview.html`. Each SVG embeds its WOFF fonts and works as an image; the README supplies the clickable links.

The design follows the reference you supplied, [Avi Vashishta's animated SVG README article](https://www.avivashishta.com/blog/github-profile-readme-animated-svg-cards). It uses paper `#f3f3f1`, ink `#111111`, blue `#2f55ff`, red `#ef3b2d`, and yellow `#ffc81a`.

The stack runs from the hero and blue contribution graph to the monthly chart, three coloured link tiles, and one card per featured repository. Each linked tile uses an image width of `32.5%` so the three share one row.

Edit `NAME`, `NAME_LINES`, `BIO`, `PROJECTS`, and the colour constants near the top of the script to personalize the cards. `NAME_LINES` controls the two visible hero lines; keep `NAME` in sync for accessible text. Project descriptions come from the public [gesture_control](https://github.com/VAMSIKRISHNA2325/gesture_control), [f1-arch](https://github.com/VAMSIKRISHNA2325/f1-arch), and [laser-surface prediction](https://github.com/VAMSIKRISHNA2325/PREDICTIVE-MODELING-OF-LASER-TREATED-METAL-SURFACES) repositories.

`assets/portrait.png` is a copy of the supplied **Tea Plantation Sunset Pop-Out Selfie** photo. Pillow turns it into ASCII rows inside the hero SVG. `PORTRAIT_CROP` focuses on the face and upper body; set it to `None` for the whole image. Set `PORTRAIT` to another local image path, or to `None` for a monogram. The original source photo is unchanged. Viewing the cards makes no portrait requests.

The bundled typefaces are [Instrument Serif](https://github.com/Instrument/instrument-serif) in regular and italic, plus [Geist and Geist Mono](https://github.com/vercel/geist-font). All use the SIL Open Font License; copies are in `assets/fonts/InstrumentSerif-OFL.txt`, `assets/fonts/Geist-OFL.txt`, and `assets/fonts/GeistMono-OFL.txt`. Font subsets are embedded separately in each card; viewing a card makes no font requests.

## Local preview

Use Python 3.12 or newer from this directory:

```sh
python -m pip install -r requirements.txt
python render_cards.py --self-test
python render_cards.py
```

The bundled JSON is enough to render offline once dependencies are installed. To fetch newer contribution data, run `python render_cards.py --refresh`, then render again.

Open `preview.html` in a browser. To capture the final frame without animations, use either:

```powershell
# PowerShell
$env:STATIC = '1'
python render_cards.py
```

```sh
# Bash
STATIC=1 python render_cards.py
```

`STATIC=1` rewrites the generated cards. Before committing or pushing, restore animated output:

```powershell
# PowerShell
Remove-Item Env:STATIC -ErrorAction SilentlyContinue
python render_cards.py
```

```sh
# Bash
STATIC=0 python render_cards.py
```

Reduced-motion preferences also show the final state in the animated cards. Delays are staggered by card order. Each image has its own clock, and browsers can pause offscreen SVGs, so exact synchronization between cards is not possible inside GitHub image tags.

## Publish and refresh daily

The profile repository is `VAMSIKRISHNA2325/VAMSIKRISHNA2325`. To publish from a fresh setup, create that **public** repository if it does not already exist, then commit and push these files to its default branch. The repository name must match the username for GitHub to display its README on the profile.

The workflow in `.github/workflows/refresh-cards.yml` runs daily at **02:17 UTC / 07:47 IST**, and can be started from **Actions → Refresh profile cards → Run workflow**. Scheduled runs become active after the workflow reaches the default branch; GitHub can delay scheduled runs. Allow Actions to write repository contents in **Settings → Actions → General → Workflow permissions**. Branch rules must also permit the bot's commits.

The workflow refreshes JSON, checks calculations, renders animated SVGs, and commits only changed contribution data, cards, and README. It uses the built-in `GITHUB_TOKEN` for committing; no personal access token is required. The bot's push does not trigger another push workflow.

## Contribution data

`--refresh` reads the public contribution calendar at <https://github.com/users/VAMSIKRISHNA2325/contributions>. It saves publicly displayed daily counts, with no private repository details. GitHub may cache the public calendar. A failed request or unexpected calendar markup stops the refresh and preserves the previous JSON; rendering remains available offline from that snapshot.

The displayed window covers 365 UTC dates through the snapshot date. Calendar-month totals can include partial months at both ends. A current streak includes the snapshot day when active; otherwise it can end yesterday so an unfinished day does not break it. Active days have at least one contribution. Busiest-day ties select the latest date. Streaks and other statistics are bounded by the saved window.

Generated files should be changed through `render_cards.py`, then rendered again. Keep font files and their licenses together when copying this project.
