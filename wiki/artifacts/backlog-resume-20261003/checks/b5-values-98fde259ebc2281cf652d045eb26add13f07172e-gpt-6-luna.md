Reviewed `98fde259ebc2281cf652d045eb26add13f07172e` against base `8bfd4b80c71bca85cb1245446d933f965b17b86a`.

Checked the complete diff, both added files, the recovery helper, `evaluation_shapes.py`, and backend typing/lint configuration. The diff adds only the two owned files; the implementation is 28 lines and preserves the recovery helper behavior while suppressing chained exceptions. The tests cover strict types, full regex matching, allowlisting, empty and missing values, nested slot failures, static error text, and input preservation. The supplied coordinator record reports passing gates and a failing allowlist mutation probe.

I did not run tests or gates, and did not verify behavior beyond this helper layer.

VERDICT: APPROVE