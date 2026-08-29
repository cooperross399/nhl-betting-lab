# Player props backtest

Does the model beat a price that was actually for sale? Calibration cannot answer that; this can, to the extent the sample allows.

- Generated: 2026-08-29T00:43:55+00:00
- Edge threshold: **0.0%**
- -3.5% over 284493 bets, 95% interval -3.8% to -3.1%. The interval excludes zero, so this sample is losing beyond chance — at this sample size and on this data, which is not the same as an edge that will persist. It also survives correcting for the 7 markets tested (-4.0% to -3.0%), which is worth more than the uncorrected number.

## Result

| Market | Bets | Profit | ROI | 95% interval | Corrected for the search | Survives |
|:-------|-----:|-------:|----:|:-------------|:-------------------------|:---------|
| **All props** | 284493 | -9838.1u | -3.5% | -3.8% .. -3.1% | -4.0% .. -3.0% | yes |
| `assists` (Assists) | 41913 | -1476.3u | -3.5% | -4.4% .. -2.7% | -4.7% .. -2.3% | yes |
| `blocked_shots` (Blocked shots) | 13863 | +213.2u | +1.5% | -0.1% .. +3.2% | -0.8% .. +3.8% | no |
| `goalie_saves` (Goalie saves) | 9361 | -383.5u | -4.1% | -6.0% .. -2.2% | -6.7% .. -1.5% | yes |
| `goals` (Goals (incl. anytime scorer)) | 10638 | -717.0u | -6.7% | -9.8% .. -3.7% | -11.0% .. -2.5% | yes |
| `points` (Points) | 77275 | -4224.1u | -5.5% | -6.2% .. -4.8% | -6.4% .. -4.5% | yes |
| `shots_on_goal` (Shots on goal) | 131443 | -3250.3u | -2.5% | -3.0% .. -1.9% | -3.2% .. -1.7% | yes |

### What each row means

- `assists`: -3.5% over 41913 bets, 95% interval -4.4% to -2.7%. The interval excludes zero, so this sample is losing beyond chance — at this sample size and on this data, which is not the same as an edge that will persist. It also survives correcting for the 7 markets tested (-4.7% to -2.3%), which is worth more than the uncorrected number.
- `blocked_shots`: +1.5% over 13863 bets, 95% interval -0.1% to +3.2%. The interval includes zero, which means **no demonstrated edge**.
- `goalie_saves`: -4.1% over 9361 bets, 95% interval -6.0% to -2.2%. The interval excludes zero, so this sample is losing beyond chance — at this sample size and on this data, which is not the same as an edge that will persist. It also survives correcting for the 7 markets tested (-6.7% to -1.5%), which is worth more than the uncorrected number.
- `goals`: -6.7% over 10638 bets, 95% interval -9.8% to -3.7%. The interval excludes zero, so this sample is losing beyond chance — at this sample size and on this data, which is not the same as an edge that will persist. It also survives correcting for the 7 markets tested (-11.0% to -2.5%), which is worth more than the uncorrected number.
- `points`: -5.5% over 77275 bets, 95% interval -6.2% to -4.8%. The interval excludes zero, so this sample is losing beyond chance — at this sample size and on this data, which is not the same as an edge that will persist. It also survives correcting for the 7 markets tested (-6.4% to -4.5%), which is worth more than the uncorrected number.
- `shots_on_goal`: -2.5% over 131443 bets, 95% interval -3.0% to -1.9%. The interval excludes zero, so this sample is losing beyond chance — at this sample size and on this data, which is not the same as an edge that will persist. It also survives correcting for the 7 markets tested (-3.2% to -1.7%), which is worth more than the uncorrected number.

### Why there are two intervals

7 figures were computed from one body of data. Under the null, the chance that at least one of 7 independent 95% tests clears is about 30% — so reporting the market that cleared, at its uncorrected interval, would be reporting a search and calling it a finding.

The corrected column is Bonferroni, which is crude and conservative. That is the right trade here: a sharper correction needs assumptions about how these markets covary, and nothing in this repository has measured that.

### The claimed edge against the realised one

The average selected bet claimed a **+4.3%** edge and the flat-stake return was **-3.5%**. That gap is not a mystery and not a fault in the measurement: bets are selected wherever the model most disagrees with the price, which is exactly where the model's own estimation error concentrates. A threshold on estimated edge harvests real edge and estimation error together, and the realised number is what is left after the error washes out.

The mean predictions themselves are close to unbiased — the walk-forward means run within a few percent of the actuals on every market — so the gap lives in the tails and in selection, not in the rates.

### Which way the bets point

This is the most important structural fact in the report, and it is not visible in the table above.

| Side | Bets | Profit | ROI | 95% interval |
|:-----|-----:|-------:|----:|:-------------|
| over | 53685 | -2513.2u | -4.7% | -5.7% .. -3.6% |
| under | 230808 | -7324.9u | -3.2% | -3.6% .. -2.8% |

**81% of every bet is on the under.** That is one directional disagreement with the market, not many independent ones: the model thinks these counts land below where the line sits, across the board. Per-market results that point in opposite directions are therefore harder to read as separate findings than the table suggests, because they rest on the same underlying bias.


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

- Priced outcomes seen: 1,261,440
- Without a model opinion: 128,182
- Below the edge threshold: 847,359
- Unparseable line or odds: 0
- Ambiguous player name, dropped: 1,406
- Bets placed: 284,493
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
