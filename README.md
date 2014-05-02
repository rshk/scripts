# Miscellaneous scripts

This repository contains random unsorted scripts that might come in
handy for various purposes..

## Contents

* ``find_broken_links.py`` Utility script to discover broken links in
  websites.
  * Uses [lxml] and [requests].
  * Uses two dbm databases to keep queue + results
  * It uses a "sort of" [breadth-first] algorithm to follow links,
    but the pop'd items from dbm are not guaranteed to be a FIFO.
  * It attempts to avoid "[spider-traps]" by limiting the depth
    to 5 (todo: make this configurable via command-line option).

[lxml]: http://lxml.de
[requests]: http://www.python-requests.org/en/latest/
[breadth-first]: http://en.wikipedia.org/wiki/Breadth-first_search
[spider-traps]: http://en.wikipedia.org/wiki/Spider_trap
