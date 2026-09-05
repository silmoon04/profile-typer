# Bundled recorded profile

The default profile is `silmoon04-v1`, published at the author's request. It is
the aggregate used by the original simulator, exported into
`src/profile_typer/data/silmoon04.json`. It contains measured distributions and
aggregate mistake variants; source sentences and raw event sequences are not
included.

| Measurement | Bundled data |
| --- | --- |
| Key-to-key intervals | 337,035 |
| Key-down/key-up hold times | 1,507 |
| Individual keys modelled | 58 |
| Key pairs modelled | 643 |
| Median key interval | 147 ms |
| Median hold time | 80.042 ms |
| Correction runs / printable events | 1,398 / 23,470, about 5.96% |
| Deleted characters in the aggregate report | 16,694 / 203,285, about 8.2% |

The sampler tries the recorded key pair, category pair, individual key, key
category, and global distribution in that order, using the original
sample-count weighting. Nine empirical quantiles provide fast and slow draws.
The preceding interval contributes a conditional rhythm distribution, keeping
some dependence between bursts and pauses.

The correction planner includes the recorded word variants, such as `teh` and
`hte` for `the`, `adn` for `and`, and `yoru` for `you`. Other words use the
recorded replacement choices plus transpositions, repeated letters, and
omissions. A correction can preserve a correct prefix or rewrite the word.
Detection and restart delays and backtrack lengths are sampled from the
aggregate. The plan is checked to recover the exact input before typing starts.

Defaults are 81.6 WPM (derived from the median key interval), corrections 1×,
and variation 100%. WPM scales the recorded cadence instead of forcing every
character to the same delay. It is a reference pace, not a promise that net WPM
will stay constant through pauses and corrections.

Correction pauses retain the original interactive bounds: 2,500 ms before
deletion and 1,500 ms before resuming, before pace scaling. Hold times are
bounded to 8–450 ms for desktop delivery. The transports serialize presses;
they do not promise exact physical-key rollover. Unicode delivery can add
platform latency, and Windows surrogate pairs are kept atomic. Deliberate
duplicate whitespace mistakes apply only to spaces, because doubling Enter or
Tab could submit a form or change fields.

The bundled aggregate SHA-256 is:

```text
485cf7530d37a20da8858d2442b5a3c6cc706f1cfa4fb97afb2fb6d2ab99930d
```

Tests verify this identity, source counts, recorded pair medians, correction
patterns, deterministic replay, and the one-time settings migration. A Linux
X11 test observes a recorded wrong spelling in a real text field, followed by
backspaces and the corrected final word.
