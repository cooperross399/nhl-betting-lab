# Player props backtest

Does the model beat a price that was actually for sale? Calibration cannot answer that; this can, to the extent the sample allows.

- Generated: 2026-08-25T23:10:55+00:00
- Edge threshold: **6.0%**
- +2.3% over 1268 bets, 95% interval -3.1% to +7.7%. The interval includes zero, which means **no demonstrated edge**.

## Result

| Market | Bets | Profit | ROI | 95% interval | Corrected for the search | Survives |
|:-------|-----:|-------:|----:|:-------------|:-------------------------|:---------|
| **All props** | 1268 | +29.3u | +2.3% | -3.1% .. +7.7% | -5.1% .. +9.7% | no |
| `assists` (Assists) | 111 | +1.0u | +0.9% | -14.2% .. +16.0% | -19.8% .. +21.7% | no |
| `blocked_shots` (Blocked shots) | 156 | +17.9u | +11.5% | -5.4% .. +28.4% | -11.7% .. +34.7% | no |
| `goalie_saves` (Goalie saves) | 23 | +10.4u | +45.1% | +13.1% .. +77.1% | +1.1% .. +89.0% | no |
| `goals` (Goals (incl. anytime scorer)) | 7 | -2.6u | -37.3% | -95.6% .. +21.0% | -117.3% .. +42.7% | no |
| `points` (Points) | 288 | -20.0u | -6.9% | -18.2% .. +4.3% | -22.3% .. +8.5% | no |
| `shots_on_goal` (Shots on goal) | 683 | +22.6u | +3.3% | -4.1% .. +10.7% | -6.9% .. +13.5% | no |

### What each row means

- `assists`: +0.9% over 111 bets, 95% interval -14.2% to +16.0%. The interval includes zero, which means **no demonstrated edge**.
- `blocked_shots`: +11.5% over 156 bets, 95% interval -5.4% to +28.4%. The interval includes zero, which means **no demonstrated edge**.
- `goalie_saves`: 23 bets is far too few to measure anything. The point estimate is +45.1% and it means nothing yet: no demonstrated edge.
- `goals`: 7 bets is far too few to measure anything. The point estimate is -37.3% and it means nothing yet: no demonstrated edge.
- `points`: -6.9% over 288 bets, 95% interval -18.2% to +4.3%. The interval includes zero, which means **no demonstrated edge**.
- `shots_on_goal`: +3.3% over 683 bets, 95% interval -4.1% to +10.7%. The interval includes zero, which means **no demonstrated edge**.

### Why there are two intervals

7 figures were computed from one body of data. Under the null, the chance that at least one of 7 independent 95% tests clears is about 30% — so reporting the market that cleared, at its uncorrected interval, would be reporting a search and calling it a finding.

The corrected column is Bonferroni, which is crude and conservative. That is the right trade here: a sharper correction needs assumptions about how these markets covary, and nothing in this repository has measured that.

### Which way the bets point

This is the most important structural fact in the report, and it is not visible in the table above.

| Side | Bets | Profit | ROI | 95% interval |
|:-----|-----:|-------:|----:|:-------------|
| over | 65 | +1.0u | +1.5% | -25.7% .. +28.7% |
| under | 1203 | +28.3u | +2.4% | -3.1% .. +7.8% |

**95% of every bet is on the under.** That is one directional disagreement with the market, not many independent ones: the model thinks these counts land below where the line sits, across the board. Per-market results that point in opposite directions are therefore harder to read as separate findings than the table suggests, because they rest on the same underlying bias.


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
- Without a model opinion: 66,442
- Below the edge threshold: 22,884
- Bets placed: 1,268

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
- Akira Schmid
- Albert Johansson
- Alec Martinez
- Alec Regula
- Aleksander Barkov
- Aleksanteri Kaskimaki
- Alex Barré-Boulet
- Alex DeBrincat
- Alex Iafallo
- Alex Kerfoot
- Alex Killorn
- Alex Laferriere
- Alex Lyon
- Alex Nedeljkovic
- Alex Newhook
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

## Which markets can be measured at all

No retention probe has been run, so which prop markets the provider retains historically is **unknown**. It is not assumed to be all of them and it is not assumed to be none.

Markets this lab prices: `shots_on_goal`, `points`, `goals`, `assists`, `goalie_saves`, `blocked_shots`. Until a retention probe has run, none of them is established as measurable or unmeasurable.

## Standing notes

- Settlement comes from the NHL boxscore, never from the odds provider. A provider outage can change what was measured; it can never change what a bet did.
- Prop prices are one-sided at most books, so the implied probability used here includes the vig. That overstates the true probability and therefore **understates** every edge below — the measurement is conservative in that one direction.
- A player who did not dress produces no bet, matching how a book voids a prop on a player who never enters.
- A market the provider does not retain historically cannot be measured historically. Those markets are named below as unmeasurable. A calibration number is not offered in their place.
- This report decides. A change that improves calibration and loses here does not ship.
