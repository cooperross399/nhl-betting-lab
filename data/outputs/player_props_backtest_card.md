# Player props backtest

Does the model beat a price that was actually for sale? Calibration cannot answer that; this can, to the extent the sample allows.

- Generated: 2026-09-02T22:27:16+00:00
- Window measured: **card**
- Edge threshold: **6.0%**
- Priced **9.6 hours before face-off** (`card` window). A return measured at one distance from the puck is not comparable to one measured at another: the lineup is known at four hours and guessed at nine.
- -0.0% over 27286 bets, 95% interval -1.2% to +1.2%. The interval includes zero, which means **no demonstrated edge**.

## Result

| Market | Bets | Profit | ROI | 95% interval | Corrected for the search | Survives |
|:-------|-----:|-------:|----:|:-------------|:-------------------------|:---------|
| **All props** | 27286 | -0.4u | -0.0% | -1.2% .. +1.2% | -1.7% .. +1.7% | no |
| `assists` (Assists) | 3609 | -35.2u | -1.0% | -3.8% .. +1.9% | -4.9% .. +3.0% | no |
| `blocked_shots` (Blocked shots) | 2894 | +243.8u | +8.4% | +4.6% .. +12.3% | +3.0% .. +13.8% | yes |
| `goalie_saves` (Goalie saves) | 110 | -2.3u | -2.1% | -19.8% .. +15.7% | -26.8% .. +22.7% | no |
| `goals` (Goals (incl. anytime scorer)) | 820 | -21.1u | -2.6% | -10.9% .. +5.8% | -14.2% .. +9.1% | no |
| `hits` (Hits) | 5021 | -60.0u | -1.2% | -3.9% .. +1.5% | -5.0% .. +2.6% | no |
| `points` (Points) | 5933 | -256.2u | -4.3% | -6.8% .. -1.8% | -7.8% .. -0.8% | yes |
| `shots_on_goal` (Shots on goal) | 8899 | +130.5u | +1.5% | -0.7% .. +3.6% | -1.5% .. +4.4% | no |

### What each row means

- `assists`: -1.0% over 3609 bets, 95% interval -3.8% to +1.9%. The interval includes zero, which means **no demonstrated edge**.
- `blocked_shots`: +8.4% over 2894 bets, 95% interval +4.6% to +12.3%. The interval excludes zero, so this sample is profitable beyond chance — at this sample size and on this data, which is not the same as an edge that will persist. It also survives correcting for the 8 markets tested (+3.0% to +13.8%), which is worth more than the uncorrected number.
- `goalie_saves`: -2.1% over 110 bets, 95% interval -19.8% to +15.7%. The interval includes zero, which means **no demonstrated edge**.
- `goals`: -2.6% over 820 bets, 95% interval -10.9% to +5.8%. The interval includes zero, which means **no demonstrated edge**.
- `hits`: -1.2% over 5021 bets, 95% interval -3.9% to +1.5%. The interval includes zero, which means **no demonstrated edge**.
- `points`: -4.3% over 5933 bets, 95% interval -6.8% to -1.8%. The interval excludes zero, so this sample is losing beyond chance — at this sample size and on this data, which is not the same as an edge that will persist. It also survives correcting for the 8 markets tested (-7.8% to -0.8%), which is worth more than the uncorrected number.
- `shots_on_goal`: +1.5% over 8899 bets, 95% interval -0.7% to +3.6%. The interval includes zero, which means **no demonstrated edge**.

### Why there are two intervals

8 figures were computed from one body of data. Under the null, the chance that at least one of 8 independent 95% tests clears is about 34% — so reporting the market that cleared, at its uncorrected interval, would be reporting a search and calling it a finding.

The corrected column is Bonferroni, which is crude and conservative. That is the right trade here: a sharper correction needs assumptions about how these markets covary, and nothing in this repository has measured that.

### The claimed edge against the realised one

The average selected bet claimed a **+10.5%** edge and the flat-stake return was **-0.0%**. That gap is not a mystery and not a fault in the measurement: bets are selected wherever the model most disagrees with the price, which is exactly where the model's own estimation error concentrates. A threshold on estimated edge harvests real edge and estimation error together, and the realised number is what is left after the error washes out.

The mean predictions themselves are close to unbiased — the walk-forward means run within a few percent of the actuals on every market — so the gap lives in the tails and in selection, not in the rates.

### Which way the bets point

This is the most important structural fact in the report, and it is not visible in the table above.

| Side | Bets | Profit | ROI | 95% interval |
|:-----|-----:|-------:|----:|:-------------|
| over | 1696 | -49.6u | -2.9% | -8.9% .. +3.0% |
| under | 25590 | +49.1u | +0.2% | -1.0% .. +1.4% |

**94% of every bet is on the under.** That is one directional disagreement with the market, not many independent ones: the model thinks these counts land below where the line sits, across the board. Per-market results that point in opposite directions are therefore harder to read as separate findings than the table suggests, because they rest on the same underlying bias.


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

- Priced outcomes seen: 685,746
- Without a model opinion: 118,837
- Below the edge threshold: 538,967
- Unparseable line or odds: 0
- Ambiguous player name, dropped: 656
- Bets placed: 27,286
- Accounted for: all of them.

Players whose prices could not be matched to a model opinion (first 50). A name here is a bet that was not measured, not a bet that lost:

- A.J. Greer
- Aaron Ekblad
- Aatu Raty
- Adam Boqvist
- Adam Edstrom
- Adam Engstrom
- Adam Erne
- Adam Fantilli
- Adam Fox
- Adam Gaudette
- Adam Ginning
- Adam Henrique
- Adam Klapka
- Adam Larsson
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
- Alex Barré-Boulet
- Alex Bump
- Alex DeBrincat
- Alex Iafallo
- Alex Kerfoot
- Alex Killorn
- Alex Laferriere
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
- Alexander Barabanov
- Alexander Holtz
- Alexander Nikishin
- Alexander Petrovic
- Alexander Romanov
- Alexander Wennberg

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
- 1,259,312 price row(s) outside the `card` window were excluded. A wager priced at two different moments is two different questions, and the better of the two is a price nobody could have taken.
