#!/usr/bin/env python

# ------------------------------------------------------------
# We take arguments on the standard input and we want to split
# them equally amongst various instances of the command.
# ------------------------------------------------------------

from __future__ import division

import sys
import subprocess
import itertools
import math


def chunks(l, n):
    """Yield successive n-sized chunks from l."""
    for i in xrange(0, len(l), n):
        yield l[i:i+n]


num_parts = int(sys.argv[1])
command = sys.argv[2:]

args = list(x.rstrip('\r\n') for x in sys.stdin)
if len(args) < num_parts:
    raise ValueError("Not enough arguments")

args_per_command = int(math.ceil(len(args) / num_parts))
partitioned_args = list(chunks(args, args_per_command))
assert len(partitioned_args) == num_parts

commands = []
for partition in partitioned_args:
    _command = list(itertools.chain(command, partition))
    commands.append(subprocess.list2cmdline(_command))

# Actually run the commands now!

subprocess.call(('tmux', 'new-window', commands[0]))
for cmd in commands[1:]:
    subprocess.call(('tmux', 'split-window', '-v', cmd))
subprocess.call(('tmux', 'select-layout', 'tiled'))
