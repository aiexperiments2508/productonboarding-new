## 1. One queue, read once

- [x] 1.1 Hold the pending queue in the shell as the array it is rather than as
      a count
- [x] 1.2 Feed the badge and the review screen from that one read, so a badge
      and a screen disagreeing is unrepresentable rather than merely fixed
- [x] 1.3 Keep the empty state's existing wording for when the queue really is
      empty, and say what is waiting when it is not

## 2. Choosing a case

- [x] 2.1 List every pending case, not only the thread this browser last started
- [x] 2.2 Carry on each row the grounds for choosing it: severity, whether
      review is mandatory, when it was raised, how many fields move, and the
      product
- [x] 2.3 Load the selected thread's checkpoint and adopt it, moving both the
      in-memory reference and the stored identifier, so re-planning and a reload
      both follow the reviewer rather than the browser's last run

## 3. The row being worked

- [x] 3.1 Mark the worked row rather than removing it, so the list does not jump
      under a reviewer mid-decision
- [x] 3.2 Mark it disabled to assistive technology rather than disabling it, so
      the row most likely to be tabbed back to stays in the tab order

## 4. Verification

- [x] 4.1 Verify against a build with three critical approvals pending and the
      stored thread identifier cleared, so the browser had raised none of them:
      badge three, list three
- [x] 4.2 Verify a selected case opens to its full change chain, its mandatory
      review grounds and a live approval action
- [x] 4.3 Verify switching cases carries the revision diff with it and returns
      the first row to open
- [x] 4.4 Verify the choice survives a reload
- [ ] 4.5 Cover the queue in the console. There is not one frontend test in this
      repository, so every claim in sections 1 to 3 is verified by using the
      application and by nothing else. The server-side property they rest on is
      asserted by `tests/test_graph.py::test_a_run_survives_the_process_being_lost`
