# Player props backtest

Does the model beat a price that was actually for sale? Calibration cannot answer that; this can, to the extent the sample allows.

- Generated: 2026-08-29T00:20:31+00:00
- Window measured: **2025-26**
- Edge threshold: **6.0%**
- -3.2% over 36449 bets, 95% interval -4.2% to -2.2%. The interval excludes zero, so this sample is losing beyond chance — at this sample size and on this data, which is not the same as an edge that will persist. It also survives correcting for the 7 markets tested (-4.6% to -1.8%), which is worth more than the uncorrected number.

## Result

| Market | Bets | Profit | ROI | 95% interval | Corrected for the search | Survives |
|:-------|-----:|-------:|----:|:-------------|:-------------------------|:---------|
| **All props** | 36449 | -1175.8u | -3.2% | -4.2% .. -2.2% | -4.6% .. -1.8% | yes |
| `assists` (Assists) | 4127 | -148.6u | -3.6% | -6.2% .. -1.0% | -7.2% .. +0.0% | no |
| `blocked_shots` (Blocked shots) | 2950 | +133.7u | +4.5% | +0.7% .. +8.3% | -0.7% .. +9.7% | no |
| `goalie_saves` (Goalie saves) | 3118 | -176.2u | -5.7% | -9.0% .. -2.3% | -10.2% .. -1.1% | yes |
| `goals` (Goals (incl. anytime scorer)) | 282 | -10.6u | -3.8% | -18.1% .. +10.6% | -23.5% .. +15.9% | no |
| `points` (Points) | 9047 | -594.4u | -6.6% | -8.6% .. -4.6% | -9.3% .. -3.8% | yes |
| `shots_on_goal` (Shots on goal) | 16925 | -379.7u | -2.2% | -3.8% .. -0.7% | -4.3% .. -0.1% | yes |

### What each row means

- `assists`: -3.6% over 4127 bets, 95% interval -6.2% to -1.0%. The interval excludes zero, so this sample is losing beyond chance — at this sample size and on this data, which is not the same as an edge that will persist. But correcting for the 7 markets tested widens it to -7.2% to +0.0%, which includes zero — so on the family of tests actually run, **no demonstrated edge**.
- `blocked_shots`: +4.5% over 2950 bets, 95% interval +0.7% to +8.3%. The interval excludes zero, so this sample is profitable beyond chance — at this sample size and on this data, which is not the same as an edge that will persist. But correcting for the 7 markets tested widens it to -0.7% to +9.7%, which includes zero — so on the family of tests actually run, **no demonstrated edge**.
- `goalie_saves`: -5.7% over 3118 bets, 95% interval -9.0% to -2.3%. The interval excludes zero, so this sample is losing beyond chance — at this sample size and on this data, which is not the same as an edge that will persist. It also survives correcting for the 7 markets tested (-10.2% to -1.1%), which is worth more than the uncorrected number.
- `goals`: -3.8% over 282 bets, 95% interval -18.1% to +10.6%. The interval includes zero, which means **no demonstrated edge**.
- `points`: -6.6% over 9047 bets, 95% interval -8.6% to -4.6%. The interval excludes zero, so this sample is losing beyond chance — at this sample size and on this data, which is not the same as an edge that will persist. It also survives correcting for the 7 markets tested (-9.3% to -3.8%), which is worth more than the uncorrected number.
- `shots_on_goal`: -2.2% over 16925 bets, 95% interval -3.8% to -0.7%. The interval excludes zero, so this sample is losing beyond chance — at this sample size and on this data, which is not the same as an edge that will persist. It also survives correcting for the 7 markets tested (-4.3% to -0.1%), which is worth more than the uncorrected number.

### Why there are two intervals

7 figures were computed from one body of data. Under the null, the chance that at least one of 7 independent 95% tests clears is about 30% — so reporting the market that cleared, at its uncorrected interval, would be reporting a search and calling it a finding.

The corrected column is Bonferroni, which is crude and conservative. That is the right trade here: a sharper correction needs assumptions about how these markets covary, and nothing in this repository has measured that.

### The claimed edge against the realised one

The average selected bet claimed a **+9.3%** edge and the flat-stake return was **-3.2%**. That gap is not a mystery and not a fault in the measurement: bets are selected wherever the model most disagrees with the price, which is exactly where the model's own estimation error concentrates. A threshold on estimated edge harvests real edge and estimation error together, and the realised number is what is left after the error washes out.

The mean predictions themselves are close to unbiased — the walk-forward means run within a few percent of the actuals on every market — so the gap lives in the tails and in selection, not in the rates.

### Which way the bets point

This is the most important structural fact in the report, and it is not visible in the table above.

| Side | Bets | Profit | ROI | 95% interval |
|:-----|-----:|-------:|----:|:-------------|
| over | 4154 | -116.0u | -2.8% | -6.0% .. +0.4% |
| under | 32295 | -1059.8u | -3.3% | -4.4% .. -2.2% |

**89% of every bet is on the under.** That is one directional disagreement with the market, not many independent ones: the model thinks these counts land below where the line sits, across the board. Per-market results that point in opposite directions are therefore harder to read as separate findings than the table suggests, because they rest on the same underlying bias.


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

- Priced outcomes seen: 603,412
- Without a model opinion: 38,131
- Below the edge threshold: 527,426
- Unparseable line or odds: 0
- Ambiguous player name, dropped: 1,406
- Bets placed: 36,449
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
- Adam Sýkora
- Adam Wilsby
- Adin Hill
- Adrian Kempe
- Akil Thomas
- Alec Regula
- Aleksanteri Kaskimaki
- Alex Bump
- Alex Kerfoot
- Alex Lyon
- Alex Nedeljkovic
- Alex Steeves
- Alex Tuch
- Alex Turcotte
- Alex Vlasic
- Alex Wennberg
- Alexander Alexeyev
- Alexander Holtz
- Alexander Nikishin
- Alexander Petrovic
- Alexander Romanov
- Alexander Wennberg
- Alexandre Carrier
- Alexandre Texier
- Alexey Toropchenko
- Aliaksei Protas
- Andre Burakovsky
- Andre Lee
- Andrei Kuzmenko
- Andrei Svechnikov
- Andrei Vasilevskiy
- Andrew Copp
- Andrew Mangiapane
- Andrew Peeke
- Anthony Cirelli
- Anthony Duclair
- Anthony Mantha
- Anthony Stolarz
- Anton Frondell

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
