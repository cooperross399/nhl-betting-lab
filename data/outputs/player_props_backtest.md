# Player props backtest

Does the model beat a price that was actually for sale? Calibration cannot answer that; this can, to the extent the sample allows.

- Generated: 2026-08-25T22:52:37+00:00
- Window measured: **2025-26**
- Edge threshold: **6.0%**
- +4.7% over 556 bets, 95% interval -3.5% to +12.8%. The interval includes zero, which means **no demonstrated edge**.

## Result

| Market | Bets | Profit | ROI | 95% interval | Corrected for the search | Survives |
|:-------|-----:|-------:|----:|:-------------|:-------------------------|:---------|
| **All props** | 556 | +25.9u | +4.7% | -3.5% .. +12.8% | -6.5% .. +15.8% | no |
| `assists` (Assists) | 72 | -1.8u | -2.4% | -21.5% .. +16.6% | -28.6% .. +23.7% | no |
| `blocked_shots` (Blocked shots) | 67 | +1.0u | +1.5% | -25.1% .. +28.0% | -35.0% .. +37.9% | no |
| `goalie_saves` (Goalie saves) | 14 | +2.9u | +20.8% | -28.2% .. +69.8% | -46.4% .. +88.0% | no |
| `goals` (Goals (incl. anytime scorer)) | 3 | -1.5u | -49.6% | -148.4% .. +49.3% | -185.2% .. +86.1% | no |
| `points` (Points) | 137 | -22.5u | -16.4% | -32.7% .. -0.1% | -38.8% .. +5.9% | no |
| `shots_on_goal` (Shots on goal) | 263 | +47.7u | +18.1% | +6.5% .. +29.8% | +2.1% .. +34.2% | yes |

### What each row means

- `assists`: -2.4% over 72 bets, 95% interval -21.5% to +16.6%. The interval includes zero, which means **no demonstrated edge**.
- `blocked_shots`: +1.5% over 67 bets, 95% interval -25.1% to +28.0%. The interval includes zero, which means **no demonstrated edge**.
- `goalie_saves`: 14 bets is far too few to measure anything. The point estimate is +20.8% and it means nothing yet: no demonstrated edge.
- `goals`: 3 bets is far too few to measure anything. The point estimate is -49.6% and it means nothing yet: no demonstrated edge.
- `points`: -16.4% over 137 bets, 95% interval -32.7% to -0.1%. The interval excludes zero, so this sample is losing beyond chance — at this sample size and on this data, which is not the same as an edge that will persist. But correcting for the 7 markets tested widens it to -38.8% to +5.9%, which includes zero — so on the family of tests actually run, **no demonstrated edge**.
- `shots_on_goal`: +18.1% over 263 bets, 95% interval +6.5% to +29.8%. The interval excludes zero, so this sample is profitable beyond chance — at this sample size and on this data, which is not the same as an edge that will persist. It also survives correcting for the 7 markets tested (+2.1% to +34.2%), which is worth more than the uncorrected number.

### Why there are two intervals

7 figures were computed from one body of data. Under the null, the chance that at least one of 7 independent 95% tests clears is about 30% — so reporting the market that cleared, at its uncorrected interval, would be reporting a search and calling it a finding.

The corrected column is Bonferroni, which is crude and conservative. That is the right trade here: a sharper correction needs assumptions about how these markets covary, and nothing in this repository has measured that.

### Which way the bets point

This is the most important structural fact in the report, and it is not visible in the table above.

| Side | Bets | Profit | ROI | 95% interval |
|:-----|-----:|-------:|----:|:-------------|
| over | 43 | +7.2u | +16.7% | -16.4% .. +49.8% |
| under | 513 | +18.7u | +3.6% | -4.7% .. +12.0% |

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

- Priced outcomes seen: 28,017
- Without a model opinion: 15,906
- Below the edge threshold: 11,555
- Bets placed: 556

Players whose prices could not be matched to a model opinion (first 50). A name here is a bet that was not measured, not a bet that lost:

- A.J. Greer
- Aaron Ekblad
- Aatu Raty
- Adam Boqvist
- Adam Edstrom
- Adam Engstrom
- Adam Erne
- Adam Fantilli
- Adam Gaudette
- Adam Ginning
- Adam Henrique
- Adam Klapka
- Adam Larsson
- Adam Lowry
- Adam Sýkora
- Adam Wilsby
- Adin Hill
- Adrian Kempe
- Akil Thomas
- Akira Schmid
- Albert Johansson
- Alec Regula
- Aleksanteri Kaskimaki
- Alex DeBrincat
- Alex Iafallo
- Alex Killorn
- Alex Laferriere
- Alex Nedeljkovic
- Alex Ovechkin
- Alex Steeves
- Alex Tuch
- Alex Turcotte
- Alex Vlasic
- Alex Wennberg
- Alexander Holtz
- Alexander Nikishin
- Alexander Petrovic
- Alexander Wennberg
- Alexandre Carrier
- Alexandre Texier
- Alexis Lafrenière
- Aliaksei Protas
- Andre Burakovsky
- Andre Lee
- Andrei Kuzmenko
- Andrei Svechnikov
- Andrew Copp
- Andrew Mangiapane
- Andrew Peeke
- Anthony Beauvillier

## Which markets can be measured at all

No retention probe has been run, so which prop markets the provider retains historically is **unknown**. It is not assumed to be all of them and it is not assumed to be none.

Markets this lab prices: `shots_on_goal`, `points`, `goals`, `assists`, `goalie_saves`, `blocked_shots`. Until a retention probe has run, none of them is established as measurable or unmeasurable.

## Standing notes

- Settlement comes from the NHL boxscore, never from the odds provider. A provider outage can change what was measured; it can never change what a bet did.
- Prop prices are one-sided at most books, so the implied probability used here includes the vig. That overstates the true probability and therefore **understates** every edge below — the measurement is conservative in that one direction.
- A player who did not dress produces no bet, matching how a book voids a prop on a player who never enters.
- A market the provider does not retain historically cannot be measured historically. Those markets are named below as unmeasurable. A calibration number is not offered in their place.
- This report decides. A change that improves calibration and loses here does not ship.
