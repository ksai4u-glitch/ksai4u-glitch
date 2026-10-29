# Profile card: setup

A neofetch-style GitHub profile card: ASCII portrait on the left, your details
and live GitHub stats on the right, in dark and light versions. A GitHub Action
rebuilds it every morning so the uptime and stats stay current.

## How it fits together

```
profile.toml ──┐
ascii.txt ─────┼──> scripts/build_card.py ──> dark_mode.svg + light_mode.svg ──> README.md shows them
GitHub API ────┘         (github_stats.py)        stats.json (last good numbers)

photo.jpg ──> scripts/ascii_portrait.py ──> ascii.txt          (you run this once, locally)

.github/workflows/update-card.yml  runs build_card.py daily at 04:17 UTC and commits the SVGs
```

| File | What it is | Do you edit it? |
|---|---|---|
| `profile.toml` | Every word on the card | Yes, this is the main one |
| `ascii.txt` | The portrait | Regenerate it from a photo |
| `scripts/build_card.py` | Turns the toml + stats into SVGs | Only to change layout/colours |
| `scripts/github_stats.py` | Read-only GitHub GraphQL queries | No |
| `scripts/ascii_portrait.py` | Photo to ASCII | No |
| `tests/test_card.py` | Checks uptime maths, alignment, stats paging | No |
| `dark_mode.svg`, `light_mode.svg`, `stats.json` | Generated | Never by hand |

## 1. Create the special repo

On GitHub: **New repository**, name it exactly **`ksai4u-glitch`** (same as your
username), make it **Public**, no template, no README. GitHub will say
"ksai4u-glitch/ksai4u-glitch is a special repository". That is the one whose
README appears on your profile page.

## 2. Push these files

From this folder:

```
git init -b main
git add .
git commit -m "Profile card"
git remote add origin https://github.com/ksai4u-glitch/ksai4u-glitch.git
git push -u origin main
```

(Or drag the whole folder into the repo's "uploading an existing file" page;
make sure the `.github` folder goes up too.)

## 3. Add a read-only token (recommended)

Without it the card still works but only counts **public** repos.
With it, your private repos' commits and lines of code are counted too
(only totals are shown, never repo names).

1. GitHub > Settings > Developer settings > Personal access tokens > **Fine-grained tokens** > Generate new token
2. Name `profile-card`, pick an expiry (put a reminder in your calendar)
3. Repository access: **All repositories**
4. Repository permissions: **Contents: Read-only** (Metadata: Read-only is added automatically). Nothing else.
5. Copy the token. In the `ksai4u-glitch` repo: Settings > Secrets and variables > Actions > **New repository secret**, name `ACCESS_TOKEN`, paste.

The workflow only ever *reads* with this token. It commits the SVGs using
GitHub's own built-in token, scoped to this one repo.

## 4. Run it once

Repo > **Actions** tab > **Update profile card** > **Run workflow**. In about a
minute the `?` placeholders in the GitHub Stats block become your real numbers.
After that it runs by itself every day.

## 5. Changing the portrait (only if you want a new one)

Your portrait is already in `ascii.txt`. It was made from your black-and-white
caricature with:

```
python scripts/ascii_portrait.py portrait.webp --invert --gamma 2 --thicken 3 --contrast 1.1 --crop-top 0
python scripts/build_card.py --offline
```

You need Python 3.11+ and Pillow (`python -m pip install pillow`) on your own PC.
On the work PC, where `Activate.ps1` is blocked, use `.venv\Scripts\python.exe`
in place of `python` in those commands.

Open `dark_mode.svg` in a browser to check it. What each option does:

* `--invert`: the background is lighter than you, so it comes out blank
* `--gamma 2`: mid-tones like skin go quiet, so the eyes, brows, smile and beard stand out
* `--thicken 3`: thin lines survive being shrunk
* `--contrast`: raise it if the result looks muddy
* `--crop-top`: head cut off? lower it; too much space above? raise it
* `--rows 26 --cols 40`: chunky big-character look, like the original card. The card
  always scales the portrait to the height of the text, so any size fits.

Push `ascii.txt` and the Action rebuilds the card.

## Editing your details

Change `profile.toml`, push, done. If a line is too long for the column,
`build_card.py` prints `warning: line is N char(s) too long` and tells you which.
Either shorten the value or raise `line_width`.

`uptime_since = "2014"` shows whole years. Use a full date like
`"2014-03-01"` (your start date in networking, or your birthday like the
original) to get the ticking "years, months, days" version.

## Checks

```
python -m unittest discover tests
```

The workflow runs these before every build, so a broken edit can't publish a
broken card.

## If something goes wrong

* **Card shows `?` for stats**: the workflow hasn't run yet, or the token is wrong.
  Open the latest run in the Actions tab; a yellow warning says why.
* **Stats stopped changing**: your token probably expired. Make a new one and
  update the `ACCESS_TOKEN` secret. The card keeps the last good numbers meanwhile.
* **Workflow fails on `git push` with 403**: repo Settings > Actions > General >
  Workflow permissions > **Read and write permissions**.
* **Profile still shows the old card**: GitHub caches images for a few minutes. Hard refresh.
