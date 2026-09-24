# Player props backtest

Does the model beat a price that was actually for sale? Calibration cannot answer that; this can, to the extent the sample allows.

- Generated: 2026-09-24T16:46:26+00:00
- Edge threshold: **6.0%**
- Priced **4.1 hours before face-off** (`late` window). A return measured at one distance from the puck is not comparable to one measured at another: the lineup is known at four hours and guessed at nine.
- -0.3% over 25911 bets, 95% interval -1.5% to +1.0%. The interval includes zero, which means **no demonstrated edge**.

## Result

| Market | Bets | Profit | ROI | 95% interval | Corrected for the search | Survives |
|:-------|-----:|-------:|----:|:-------------|:-------------------------|:---------|
| **All props** | 25911 | -69.0u | -0.3% | -1.5% .. +1.0% | -1.9% .. +1.4% | no |
| `assists` (Assists) | 3761 | -48.3u | -1.3% | -4.0% .. +1.5% | -5.1% .. +2.5% | no |
| `blocked_shots` (Blocked shots) | 4286 | +211.7u | +4.9% | +1.8% .. +8.1% | +0.6% .. +9.3% | yes |
| `goalie_saves` (Goalie saves) | 1727 | -42.7u | -2.5% | -6.9% .. +2.0% | -8.6% .. +3.7% | no |
| `goals` (Goals (incl. anytime scorer)) | 564 | -38.1u | -6.8% | -17.2% .. +3.7% | -21.1% .. +7.6% | no |
| `points` (Points) | 6194 | -274.8u | -4.4% | -6.9% .. -2.0% | -7.8% .. -1.0% | yes |
| `shots_on_goal` (Shots on goal) | 9379 | +123.2u | +1.3% | -0.8% .. +3.4% | -1.5% .. +4.2% | no |

### What each row means

- `assists`: -1.3% over 3761 bets, 95% interval -4.0% to +1.5%. The interval includes zero, which means **no demonstrated edge**.
- `blocked_shots`: +4.9% over 4286 bets, 95% interval +1.8% to +8.1%. The interval excludes zero, so this sample is profitable beyond chance — at this sample size and on this data, which is not the same as an edge that will persist. It also survives correcting for the 7 markets tested (+0.6% to +9.3%), which is worth more than the uncorrected number.
- `goalie_saves`: -2.5% over 1727 bets, 95% interval -6.9% to +2.0%. The interval includes zero, which means **no demonstrated edge**.
- `goals`: -6.8% over 564 bets, 95% interval -17.2% to +3.7%. The interval includes zero, which means **no demonstrated edge**.
- `points`: -4.4% over 6194 bets, 95% interval -6.9% to -2.0%. The interval excludes zero, so this sample is losing beyond chance — at this sample size and on this data, which is not the same as an edge that will persist. It also survives correcting for the 7 markets tested (-7.8% to -1.0%), which is worth more than the uncorrected number.
- `shots_on_goal`: +1.3% over 9379 bets, 95% interval -0.8% to +3.4%. The interval includes zero, which means **no demonstrated edge**.

### Why there are two intervals

7 figures were computed from one body of data. Under the null, the chance that at least one of 7 independent 95% tests clears is about 30% — so reporting the market that cleared, at its uncorrected interval, would be reporting a search and calling it a finding.

The corrected column is Bonferroni, which is crude and conservative. That is the right trade here: a sharper correction needs assumptions about how these markets covary, and nothing in this repository has measured that.

### The claimed edge against the realised one

The average selected bet claimed a **+9.4%** edge and the flat-stake return was **-0.3%**. That gap is not a mystery and not a fault in the measurement: bets are selected wherever the model most disagrees with the price, which is exactly where the model's own estimation error concentrates. A threshold on estimated edge harvests real edge and estimation error together, and the realised number is what is left after the error washes out.

The mean predictions themselves are close to unbiased — the walk-forward means run within a few percent of the actuals on every market — so the gap lives in the tails and in selection, not in the rates.

### Which way the bets point

This is the most important structural fact in the report, and it is not visible in the table above.

| Side | Bets | Profit | ROI | 95% interval |
|:-----|-----:|-------:|----:|:-------------|
| over | 2568 | -115.1u | -4.5% | -8.9% .. -0.1% |
| under | 23343 | +46.1u | +0.2% | -1.1% .. +1.5% |

**90% of every bet is on the under.** That is one directional disagreement with the market, not many independent ones: the model thinks these counts land below where the line sits, across the board. Per-market results that point in opposite directions are therefore harder to read as separate findings than the table suggests, because they rest on the same underlying bias.


Every number above is a point estimate from a finite sample. An interval that includes zero means **no demonstrated edge** — not 'promising', not 'trending positive'.

### How much data would settle it

| If the true edge were | Bets needed to separate it from zero |
|----------------------:|-------------------------------------:|
| +5% | ~1,537 |
| +8% | ~601 |
| +10% | ~385 |
| +15% | ~171 |

Order-of-magnitude guidance rather than a precise power calculation. Its job is to make 'we cannot know this yet' concrete.

## Where the bets came from

- Priced outcomes seen: 550,225
- Without a model opinion: 74,226
- Below the edge threshold: 449,484
- Unparseable line or odds: 0
- Ambiguous player name, dropped: 604
- Bets placed: 25,911
- Accounted for: all of them.

Players whose prices could not be matched to a model opinion (first 50). A name here is a bet that was not measured, not a bet that lost:

- A.J. Greer
- Aaron Ekblad
- Aatu Raty
- Adam Boqvist
- Adam Edstrom
- Adam Engstrom
- Adam Erne
- Adam Gaudette
- Adam Ginning
- Adam Henrique
- Adam Klapka
- Adam Lowry
- Adam Pelech
- Adam Sýkora
- Adam Wilsby
- Adin Hill
- Adrian Kempe
- Akil Thomas
- Albert Johansson
- Alec Martinez
- Alec Regula
- Aleksander Barkov
- Aleksanteri Kaskimaki
- Aleksei Kolosov
- Alex Barré-Boulet
- Alex Bump
- Alex Iafallo
- Alex Kerfoot
- Alex Laferriere
- Alex Lyon
- Alex Nedeljkovic
- Alex Newhook
- Alex Nylander
- Alex Ovechkin
- Alex Pietrangelo
- Alex Steeves
- Alex Tuch
- Alex Turcotte
- Alex Vlasic
- Alex Wennberg
- Alexandar Georgiev
- Alexander Alexeyev
- Alexander Holtz
- Alexander Nikishin
- Alexander Petrovic
- Alexander Romanov
- Alexander Wennberg
- Alexandre Carrier
- Alexandre Texier
- Alexey Toropchenko

## Which markets can be measured at all

| Provider market | Events probed | Seen in | Verdict |
|:----------------|--------------:|--------:|:--------|
| `player_shots_on_goal` | 5432 | 5431 | measurable (5431/5432) |
| `player_points` | 5432 | 5431 | measurable (5431/5432) |
| `player_goals` | 5432 | 5431 | measurable (5431/5432) |
| `player_assists` | 5432 | 5431 | measurable (5431/5432) |
| `player_total_saves` | 5432 | 2570 | measurable (2570/5432) |
| `player_blocked_shots` | 5432 | 4715 | measurable (4715/5432) |
| `player_hits` | 5432 | 1218 | measurable (1218/5432) |

## Standing notes

- Settlement comes from the NHL boxscore, never from the odds provider. A provider outage can change what was measured; it can never change what a bet did.
- Prop prices are one-sided at most books, so the implied probability used here includes the vig. That overstates the true probability and therefore **understates** every edge below — the measurement is conservative in that one direction.
- A player who did not dress produces no bet, matching how a book voids a prop on a player who never enters.
- A market the provider does not retain historically cannot be measured historically. Any such market is named below as unmeasurable, and a calibration number is not offered in its place; when no market is named there, none was found to be unmeasurable.
- This report decides. A change that improves calibration and loses here does not ship.
- 2,544,921 price row(s) outside the `late` window were excluded. A wager priced at two different moments is two different questions, and the better of the two is a price nobody could have taken.
