# Player props backtest

Does the model beat a price that was actually for sale? Calibration cannot answer that; this can, to the extent the sample allows.

- Generated: 2026-08-31T20:34:13+00:00
- Edge threshold: **6.0%**
- -0.3% over 25949 bets, 95% interval -1.5% to +0.9%. The interval includes zero, which means **no demonstrated edge**.

## Result

| Market | Bets | Profit | ROI | 95% interval | Corrected for the search | Survives |
|:-------|-----:|-------:|----:|:-------------|:-------------------------|:---------|
| **All props** | 25949 | -76.7u | -0.3% | -1.5% .. +0.9% | -2.0% .. +1.4% | no |
| `assists` (Assists) | 3762 | -54.1u | -1.4% | -4.2% .. +1.3% | -5.2% .. +2.3% | no |
| `blocked_shots` (Blocked shots) | 4293 | +213.0u | +5.0% | +1.8% .. +8.1% | +0.6% .. +9.3% | yes |
| `goalie_saves` (Goalie saves) | 1733 | -43.1u | -2.5% | -6.9% .. +2.0% | -8.6% .. +3.6% | no |
| `goals` (Goals (incl. anytime scorer)) | 564 | -38.1u | -6.8% | -17.2% .. +3.7% | -21.1% .. +7.6% | no |
| `points` (Points) | 6202 | -273.9u | -4.4% | -6.9% .. -1.9% | -7.8% .. -1.0% | yes |
| `shots_on_goal` (Shots on goal) | 9395 | +119.5u | +1.3% | -0.8% .. +3.4% | -1.6% .. +4.1% | no |

### What each row means

- `assists`: -1.4% over 3762 bets, 95% interval -4.2% to +1.3%. The interval includes zero, which means **no demonstrated edge**.
- `blocked_shots`: +5.0% over 4293 bets, 95% interval +1.8% to +8.1%. The interval excludes zero, so this sample is profitable beyond chance — at this sample size and on this data, which is not the same as an edge that will persist. It also survives correcting for the 7 markets tested (+0.6% to +9.3%), which is worth more than the uncorrected number.
- `goalie_saves`: -2.5% over 1733 bets, 95% interval -6.9% to +2.0%. The interval includes zero, which means **no demonstrated edge**.
- `goals`: -6.8% over 564 bets, 95% interval -17.2% to +3.7%. The interval includes zero, which means **no demonstrated edge**.
- `points`: -4.4% over 6202 bets, 95% interval -6.9% to -1.9%. The interval excludes zero, so this sample is losing beyond chance — at this sample size and on this data, which is not the same as an edge that will persist. It also survives correcting for the 7 markets tested (-7.8% to -1.0%), which is worth more than the uncorrected number.
- `shots_on_goal`: +1.3% over 9395 bets, 95% interval -0.8% to +3.4%. The interval includes zero, which means **no demonstrated edge**.

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
| over | 2572 | -115.3u | -4.5% | -8.9% .. -0.1% |
| under | 23377 | +38.6u | +0.2% | -1.1% .. +1.4% |

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

- Priced outcomes seen: 551,228
- Without a model opinion: 74,381
- Below the edge threshold: 450,294
- Unparseable line or odds: 0
- Ambiguous player name, dropped: 604
- Bets placed: 25,949
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
| `player_hits` | 256 | 0 | **not offered in any of 256 events** |

### Named as unmeasurable

- `hits`: Not offered in any historical snapshot across 256 probed events spanning two seasons, so it cannot be measured against past prices. It is served live; its evidence must accumulate forward.

These markets have **no price-based evidence at all**. Whatever their calibration says, it cannot substitute for this, and no report in this repository will present it as though it does.

## Standing notes

- Settlement comes from the NHL boxscore, never from the odds provider. A provider outage can change what was measured; it can never change what a bet did.
- Prop prices are one-sided at most books, so the implied probability used here includes the vig. That overstates the true probability and therefore **understates** every edge below — the measurement is conservative in that one direction.
- A player who did not dress produces no bet, matching how a book voids a prop on a player who never enters.
- A market the provider does not retain historically cannot be measured historically. Those markets are named below as unmeasurable. A calibration number is not offered in their place.
- This report decides. A change that improves calibration and loses here does not ship.
