# Player props backtest

Does the model beat a price that was actually for sale? Calibration cannot answer that; this can, to the extent the sample allows.

- Generated: 2026-08-27T05:59:03+00:00
- Edge threshold: **6.0%**
- +1.4% over 4830 bets, 95% interval -1.4% to +4.2%. The interval includes zero, which means **no demonstrated edge**.

## Result

| Market | Bets | Profit | ROI | 95% interval | Corrected for the search | Survives |
|:-------|-----:|-------:|----:|:-------------|:-------------------------|:---------|
| **All props** | 4830 | +68.7u | +1.4% | -1.4% .. +4.2% | -2.4% .. +5.3% | no |
| `assists` (Assists) | 403 | -18.0u | -4.5% | -13.0% .. +4.1% | -16.2% .. +7.3% | no |
| `blocked_shots` (Blocked shots) | 548 | +65.2u | +11.9% | +3.2% .. +20.6% | -0.1% .. +23.9% | no |
| `goalie_saves` (Goalie saves) | 397 | -6.8u | -1.7% | -10.9% .. +7.5% | -14.3% .. +10.9% | no |
| `goals` (Goals (incl. anytime scorer)) | 34 | +3.6u | +10.6% | -34.8% .. +56.0% | -51.8% .. +73.0% | no |
| `points` (Points) | 940 | -51.8u | -5.5% | -11.9% .. +0.9% | -14.3% .. +3.3% | no |
| `shots_on_goal` (Shots on goal) | 2508 | +76.5u | +3.0% | -0.9% .. +7.0% | -2.4% .. +8.5% | no |

### What each row means

- `assists`: -4.5% over 403 bets, 95% interval -13.0% to +4.1%. The interval includes zero, which means **no demonstrated edge**.
- `blocked_shots`: +11.9% over 548 bets, 95% interval +3.2% to +20.6%. The interval excludes zero, so this sample is profitable beyond chance — at this sample size and on this data, which is not the same as an edge that will persist. But correcting for the 7 markets tested widens it to -0.1% to +23.9%, which includes zero — so on the family of tests actually run, **no demonstrated edge**.
- `goalie_saves`: -1.7% over 397 bets, 95% interval -10.9% to +7.5%. The interval includes zero, which means **no demonstrated edge**.
- `goals`: +10.6% over 34 bets, 95% interval -34.8% to +56.0%. The interval includes zero, which means **no demonstrated edge**.
- `points`: -5.5% over 940 bets, 95% interval -11.9% to +0.9%. The interval includes zero, which means **no demonstrated edge**.
- `shots_on_goal`: +3.0% over 2508 bets, 95% interval -0.9% to +7.0%. The interval includes zero, which means **no demonstrated edge**.

### Why there are two intervals

7 figures were computed from one body of data. Under the null, the chance that at least one of 7 independent 95% tests clears is about 30% — so reporting the market that cleared, at its uncorrected interval, would be reporting a search and calling it a finding.

The corrected column is Bonferroni, which is crude and conservative. That is the right trade here: a sharper correction needs assumptions about how these markets covary, and nothing in this repository has measured that.

### The claimed edge against the realised one

The average selected bet claimed a **+9.4%** edge and the flat-stake return was **+1.4%**. That gap is not a mystery and not a fault in the measurement: bets are selected wherever the model most disagrees with the price, which is exactly where the model's own estimation error concentrates. A threshold on estimated edge harvests real edge and estimation error together, and the realised number is what is left after the error washes out.

The mean predictions themselves are close to unbiased — the walk-forward means run within a few percent of the actuals on every market — so the gap lives in the tails and in selection, not in the rates.

### Which way the bets point

This is the most important structural fact in the report, and it is not visible in the table above.

| Side | Bets | Profit | ROI | 95% interval |
|:-----|-----:|-------:|----:|:-------------|
| over | 378 | -12.8u | -3.4% | -14.7% .. +8.0% |
| under | 4452 | +81.5u | +1.8% | -1.1% .. +4.7% |

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
- Without a model opinion: 5,458
- Below the edge threshold: 80,282
- Unparseable line or odds: 0
- Ambiguous player name, dropped: 24
- Bets placed: 4,830
- Accounted for: all of them.

Players whose prices could not be matched to a model opinion (first 50). A name here is a bet that was not measured, not a bet that lost:

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
- Ben Hutton

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
