#!/usr/bin/env python
"""Summarize statistics of call correctness across multiple parameters.

Usage:
  summarize_stats.py <stats file in YAML format>
"""
import sys
import collections

import yaml

def main(in_file):
    with open(in_file) as in_handle:
        stats = yaml.load(in_handle)
    regions = ["rt", "gag"]
    for region in regions:
        print region
        rstats = [(float(s["qual"]), float(s["kmer"]), s)
                  for s in stats if s["region"] == region]
        rstats.sort()
        for (_, _, info) in rstats:
            summarize_counts(info)

def summarize_counts(info):
    names = ["single", ">=5%", "<5%"]
    selects = [lambda x: x["percent"] == 100.0,
               lambda x: x["percent"] < 100.0 and x["percent"] >= 5.0,
               lambda x: x["percent"] < 5.0]
    print " quality: %s, kmer %s" % (info["qual"], info["kmer"])
    for name, select in zip(names, selects):
        vals = collections.defaultdict(int)
        for d in filter(select, info["calls"]):
            for k, v in d.iteritems():
                if k != "percent":
                    vals[k] += v
        total = float(sum(vals.values()))
        right = vals["correct"]
        wrong = vals["wrong"] + vals["partial"]
        print "% 8s:  Correct % 4s (%.1f%%); Wrong % 3s (%.1f%%)" % \
              (name, right, right / total * 100.0, wrong, wrong / total * 100.0)

if __name__ == "__main__":
    main(*sys.argv[1:])
