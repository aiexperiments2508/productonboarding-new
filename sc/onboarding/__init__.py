"""Onboarding a batch of products a supplier sent in one bundle.

Three modules, in the order a batch moves through them:

*   ``batch``  - which products a bundle touched, read back from its submission
*   ``assess`` - the sequential pass over those products, one at a time
*   ``fix``    - applying the fills a model could cite, and nothing else

Deliberately not a LangGraph run. The correction graph answers *a published
value changed, what does it reach*; onboarding asks *is this record fit to
launch*, which is what the readiness checks already answer, deterministically
and in milliseconds. Working forty new products through a graph that ends at an
approval interrupt would leave forty suspended threads and forty pending
approvals in a queue that exists to hold one.
"""
