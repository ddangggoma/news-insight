"""Small-sample statistics shared by the radar scores and signal rules (checklist STAT-3).

One family of tests for every rule, so a new rule does not bring its own floor or ratio:

- counts against earlier windows: an overdispersed Poisson z (variance at least the mean, as in a
  negative binomial, never below 1), so ten reports on a base of five is not "7σ"; the observed
  spread is taken from successive differences, so a steady decline is not mistaken for noise;
- a count against an expected rate: the Poisson z;
- a share against an earlier share: the two-proportion z with a pooled standard error;
- "none at all" (no Korean source): the binomial chance of zero hits at the usual rate;
- rankings: shares shrunk toward the overall share (empirical Bayes), so a theme with three
  reports cannot outrank one with thirty on a lucky ratio. Eligibility uses the plain share and
  CARD_MIN reports.
"""

from collections.abc import Sequence
from math import sqrt
from statistics import fmean

SIGNIFICANT_Z = 2.0  # one-sided, about 2.3 %
PRIOR_REPORTS = 10.0  # weight of the overall share when shrinking a topic's share
CARD_MIN = 5  # reports a topic needs in the window before a rule reads anything into its mix


def noise_variance(history: Sequence[float]) -> float:
    """Half the mean squared successive difference (von Neumann): the window-to-window noise
    without the part a trend adds to the plain variance."""
    if len(history) < 2:
        return 0.0
    steps = [(b - a) ** 2 for a, b in zip(history, history[1:], strict=False)]
    return fmean(steps) / 2


def count_z(current: float, history: Sequence[float]) -> float:
    """Current count against earlier windows; the variance is the larger of the observed noise,
    the mean (Poisson) and 1."""
    mean = fmean(history) if history else 0.0
    return (current - mean) / sqrt(max(noise_variance(history), mean, 1.0))


def rate_z(observed: float, expected: float) -> float:
    """Poisson z of an observed count against the expected one (at least 1)."""
    return (observed - expected) / sqrt(max(expected, 1.0))


def two_proportion_z(x1: float, n1: float, x2: float, n2: float) -> float:
    """z of x1/n1 − x2/n2 with a pooled standard error; 0 when either side is empty."""
    if n1 <= 0 or n2 <= 0:
        return 0.0
    pooled = (x1 + x2) / (n1 + n2)
    se = sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
    return (x1 / n1 - x2 / n2) / se if se else 0.0


def zero_chance(n: int, rate: float) -> float:
    """Chance of no hits in n independent reports at the given rate."""
    return (1.0 - min(max(rate, 0.0), 1.0)) ** n


def shrunk_share(x: float, n: float, prior: float, weight: float = PRIOR_REPORTS) -> float:
    """x/n pulled toward `prior` as if `weight` reports at the prior share were added."""
    return (x + prior * weight) / (n + weight) if n + weight > 0 else prior
