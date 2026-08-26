# Player props backtest

Does the model beat a price that was actually for sale? Calibration cannot answer that; this can, to the extent the sample allows.

- Generated: 2026-08-26T03:01:41+00:00
- Edge threshold: **6.0%**
- +1.2% over 4777 bets, 95% interval -1.7% to +4.0%. The interval includes zero, which means **no demonstrated edge**.

## Result

| Market | Bets | Profit | ROI | 95% interval | Corrected for the search | Survives |
|:-------|-----:|-------:|----:|:-------------|:-------------------------|:---------|
| **All props** | 4777 | +56.3u | +1.2% | -1.7% .. +4.0% | -2.7% .. +5.1% | no |
| `assists` (Assists) | 386 | -23.4u | -6.1% | -14.8% .. +2.7% | -18.1% .. +6.0% | no |
| `blocked_shots` (Blocked shots) | 555 | +65.7u | +11.8% | +3.2% .. +20.5% | -0.1% .. +23.7% | no |
| `goalie_saves` (Goalie saves) | 410 | -10.3u | -2.5% | -11.6% .. +6.6% | -14.9% .. +9.9% | no |
| `goals` (Goals (incl. anytime scorer)) | 37 | +5.5u | +14.8% | -29.4% .. +59.0% | -45.8% .. +75.5% | no |
| `points` (Points) | 913 | -41.1u | -4.5% | -11.1% .. +2.0% | -13.5% .. +4.5% | no |
| `shots_on_goal` (Shots on goal) | 2476 | +59.9u | +2.4% | -1.5% .. +6.4% | -3.0% .. +7.9% | no |

### What each row means

- `assists`: -6.1% over 386 bets, 95% interval -14.8% to +2.7%. The interval includes zero, which means **no demonstrated edge**.
- `blocked_shots`: +11.8% over 555 bets, 95% interval +3.2% to +20.5%. The interval excludes zero, so this sample is profitable beyond chance — at this sample size and on this data, which is not the same as an edge that will persist. But correcting for the 7 markets tested widens it to -0.1% to +23.7%, which includes zero — so on the family of tests actually run, **no demonstrated edge**.
- `goalie_saves`: -2.5% over 410 bets, 95% interval -11.6% to +6.6%. The interval includes zero, which means **no demonstrated edge**.
- `goals`: +14.8% over 37 bets, 95% interval -29.4% to +59.0%. The interval includes zero, which means **no demonstrated edge**.
- `points`: -4.5% over 913 bets, 95% interval -11.1% to +2.0%. The interval includes zero, which means **no demonstrated edge**.
- `shots_on_goal`: +2.4% over 2476 bets, 95% interval -1.5% to +6.4%. The interval includes zero, which means **no demonstrated edge**.

### Why there are two intervals

7 figures were computed from one body of data. Under the null, the chance that at least one of 7 independent 95% tests clears is about 30% — so reporting the market that cleared, at its uncorrected interval, would be reporting a search and calling it a finding.

The corrected column is Bonferroni, which is crude and conservative. That is the right trade here: a sharper correction needs assumptions about how these markets covary, and nothing in this repository has measured that.

### The claimed edge against the realised one

The average selected bet claimed a **+9.4%** edge and the flat-stake return was **+1.2%**. That gap is not a mystery and not a fault in the measurement: bets are selected wherever the model most disagrees with the price, which is exactly where the model's own estimation error concentrates. A threshold on estimated edge harvests real edge and estimation error together, and the realised number is what is left after the error washes out.

The mean predictions themselves are close to unbiased — the walk-forward means run within a few percent of the actuals on every market — so the gap lives in the tails and in selection, not in the rates.

### Which way the bets point

This is the most important structural fact in the report, and it is not visible in the table above.

| Side | Bets | Profit | ROI | 95% interval |
|:-----|-----:|-------:|----:|:-------------|
| over | 400 | -2.6u | -0.7% | -11.7% .. +10.4% |
| under | 4377 | +58.9u | +1.3% | -1.6% .. +4.3% |

**92% of every bet is on the under.** That is one directional disagreement with the market, not many independent ones: the model thinks these counts land below where the line sits, across the board. Per-market results that point in opposite directions are therefore harder to read as separate findings than the table suggests, because they rest on the same underlying bias.


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

- Priced outcomes seen: 90,594
- Without a model opinion: 5,478
- Below the edge threshold: 80,339
- Bets placed: 4,777

Players whose prices could not be matched to a model opinion (first 50). A name here is a bet that was not measured, not a bet that lost:

- A.J. Greer
- Aatu Raty
- Adam Boqvist
- Adam Edstrom
- Adam Engstrom
- Adam Erne
- Adam Gaudette
- Adam Ginning
- Adam Klapka
- Adam Sýkora
- Adam Wilsby
- Akil Thomas
- Albert Johansson
- Alec Martinez
- Aleksanteri Kaskimaki
- Alex Barré-Boulet
- Alex Kerfoot
- Alex Pietrangelo
- Alex Steeves
- Alex Turcotte
- Alex Wennberg
- Alexandar Georgiev
- Alexander Alexeyev
- Alexander Holtz
- Alexander Romanov
- Alexandre Carrier
- Alexandre Texier
- Alexey Toropchenko
- Andre Burakovsky
- Andre Lee
- Andreas Athanasiou
- Andreas Englund
- Andrei Kuzmenko
- Andrei Svechnikov
- Andrei Vasilevskiy
- Angus Crookshank
- Anthony Duclair
- Anthony Richard
- Anthony Stolarz
- Arber Xhekaj
- Arseny Gritsyuk
- Arshdeep Bains
- Artem Zub
- Artemi Panarin
- Arthur Kaliyev
- Artyom Levshunov
- Austin Watson
- Auston Matthews
- Axel Sandin Pellikka
- Barrett Hayton

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
