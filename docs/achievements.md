The README achievement cards use the profile's existing terminal colors and
official GitHub badge artwork. They show every earned tier, with an expandable
text table linking to the activity GitHub lists in each badge's history.

The data is a verified snapshot dated 17 November 2026, not a live counter.
Only earned badges and tiers belong in `assets/achievements/history.json`.

All dates display in EAT (UTC+3):

- `github_unlock`: the base badge's exact `relative-time` timestamp from its
  GitHub achievement history.
- `milestone_activity`: a later tier's linked PR `mergedAt` or discussion
  `answerChosenAt` timestamp. GitHub's public achievement history does not
  provide a separate unlock timestamp for each later tier. The card labels
  these dates as milestones.

This distinction matters for Pair Extraordinaire: the badge first unlocked on
3 October 2026 even though its linked PR merged on 26 September 2026. Do not
substitute a merge date for the recorded base unlock date. Also, the sidebar's
`x3` means three earned tiers (Base, Bronze, Silver), not three contributions.

To update the section:

1. Open `https://github.com/Antech-greyhat?tab=achievements` and inspect each
   badge's History. Check the exact `datetime` for the base badge and the
   sources listed for every earned tier.
2. Verify new tier dates from the linked PR's `mergedAt` or discussion's
   `answerChosenAt`. Update the JSON history and `verified_on` date.
3. If a badge's image changes, save its official PNG in
   `assets/achievements/` and update its `badge_image_url` for provenance.
4. Run `python .github/scripts/achievements.py` from any directory. The script
   needs no packages or network access. It regenerates the cards and only the
   README block between the achievement markers.

The SVGs embed the local PNGs so images still work when GitHub displays SVGs
through its image proxy. The README also provides descriptive alt text and a
native `<details>` table for selectable text and keyboard access.
