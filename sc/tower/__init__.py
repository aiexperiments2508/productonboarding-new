"""The control tower: one place that joins what the rest already derives.

Four questions, none of which any single existing surface can answer:

    flow      where is every feed's product, from received to on sale
    register  what has arrived, feed by feed, over a window
    kpis      how well is this working, in numbers an executive can quote
    spend     what did the models cost, and what did the cache save

Nothing here decides anything. Every verdict, stage, gate outcome and lane is
read from the module that already owns it - ``sc.readiness``, ``sc.lifecycle``,
``sc.onboarding`` - and this package only counts and joins. That is the same
rule ``sc/readiness/rollup.py`` states for itself, and it matters more here: a
dashboard that reached its own conclusion would be a second answer to "is this
ready", and the one on the big screen is the one people would quote.

There is no snapshot table and no stored rollup. Every number is recomputed on
read, for the reason ``sc/lifecycle/stages.py`` gives for not storing a stage:
a stored figure is a second account of the truth, and the first thing it
disagrees about is whatever somebody just changed.
"""
