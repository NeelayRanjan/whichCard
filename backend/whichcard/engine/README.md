# Resolution order
Match fields are ANDed. Merchant inference resolves query/category/app first. For
an unknown category, only matching flat-rate rules apply. Rules outside their
active dates are excluded. Activation-required rules warn and are excluded until
`settings.activated_<zero-based earn rule index>: true` is set in wallet.yaml.

Matching rules sort by multiplier descending. Calendar/anniversary caps subtract
eligible purchases minus refunds in their period, through the context date. Shared
`cap.group` rules share spending. A purchase crossing a cap is split across the
remaining higher rate and the next rule; an exhausted cap falls through. Refunds
restore cap room, with consumed spend floored at zero. Fees/payments never consume
caps. Historical simulations exclude later transactions.

Multiply the resulting weighted multiplier by the selected point valuation,
subtract foreign fees, then add matched offers. `reward_rate_pct` is bounded by
the maximum multiplier times valuation; `effective_rate_pct` includes offers and
can exceed that bound. With amount unknown, fixed-dollar offers cannot affect
ranking. Offers are manually maintained and assumed unused/eligible.

An at-risk, uncompleted sign-up bonus moves its card first. Remaining ties use
lower latest-statement utilization, then oldest last purchase, then card id for
stability. Range uses cash-out and optimized valuations; typical drives ranking.
