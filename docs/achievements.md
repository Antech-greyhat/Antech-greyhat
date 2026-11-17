The README achievement cards update automatically from the badges GitHub
actually shows on the profile. New badge types are discovered from the earned
achievement cards rather than a fixed list. When a new tier appears, the
updater fetches its history and official artwork, verifies available dates,
and regenerates the JSON, SVG cards, and README section together.

The `Refresh GitHub Achievements` workflow checks every five minutes, at
minutes 2, 7, 12, etc. It also runs after pushes to `main`, a manual **Run
workflow**, or a `repository_dispatch` event of type `achievement-refresh`.
Pull requests run the offline tests without publishing changes. Routine
unchanged checks make one public-page request and reuse saved badge histories
and images. Only changed files are committed; the verification date advances
once per day rather than creating a commit every five minutes.

GitHub does not expose an achievement-unlock webhook, so this is automatic
polling rather than an instantaneous update. Its shortest Actions interval is
five minutes, scheduled jobs can be delayed or dropped, and image caching can
delay display after a successful refresh. Scheduled workflows must be on the
default branch; merge this change into `main` to activate the schedule.
GitHub can disable schedules after 60 days without repository activity.
See [GitHub's schedule documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

No extra secret is needed for public milestone activity: the workflow uses
its built-in `GITHUB_TOKEN`. If a linked milestone requires private-repository
access, an optional `ACHIEVEMENTS_TOKEN` can provide that access. GitHub's
public badge history may omit private sources; missing dates display as
`Not published`, never as a made-up unlock date.

All dates display in EAT (UTC+3):

- `github_unlock`: the base badge's exact `relative-time` timestamp from its
  GitHub achievement history.
- `github_tier_unlock`: a tier-specific timestamp if GitHub supplies one.
- `milestone_activity`: a later tier's linked PR `mergedAt`, issue `closedAt`,
  or discussion `answerChosenAt`. These display as milestone dates. Saved
  verified dates are retained if the same milestone is encountered again.
- `unavailable`: GitHub does not provide a verifiable date for that tier.

Pair Extraordinaire first unlocked on 3 October 2026 even though its linked
PR merged on 26 September. The updater preserves the recorded base unlock
date. The sidebar's `x3` means three earned tiers, not three contributions.
Cards grow vertically when Gold or further tiers appear so dates are not
clipped.

If GitHub returns an error, incomplete badge list, fewer tiers, invalid image,
or malformed history, the updater exits before changing generated files. The
last verified README stays visible and the failed Actions run records the
error. Because public HTML is used for badge discovery, a future GitHub HTML
change may need a parser update.

For a local refresh, run `python .github/scripts/sync_achievements.py` with
`GITHUB_TOKEN` set or an authenticated GitHub CLI. `--force` rechecks all badge
histories; `--dry-run` verifies without writing. Both options can be combined.
For offline regeneration, run `python .github/scripts/achievements.py`.
Run the checks with `python -m unittest discover -s tests`.

The SVGs embed their local PNG artwork for GitHub's image proxy. The README
provides descriptive alt text and a native `<details>` table for selectable
text and keyboard access. Only the block between the achievement markers is
regenerated.
