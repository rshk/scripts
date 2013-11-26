#!/usr/bin/env python
"""
Scan a website to find broken links and compile a report.
"""

from __future__ import print_function

from collections import defaultdict
import anydbm
import json
import sys
import traceback
import urlparse

missing_deps = []

try:
    import requests
except ImportError:
    missing_deps.append('requests')

try:
    import lxml.html
except ImportError:
    missing_deps.append('lxml')

if len(missing_deps):
    print("Missing dependencies: {0}".format(' '.join(missing_deps)))
    sys.exit(1)


class ResultRecord(object):
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    @property
    def url(self):
        return self.kwargs['url']

    @property
    def links(self):
        return self.kwargs.get('links') or set()

    @property
    def headers(self):
        return self.kwargs.get('headers') or {}

    @property
    def status(self):
        return self.kwargs.get('status') or None

    @property
    def exception(self):
        return self.kwargs.get('exception') or None

    @property
    def ok(self):
        return (self.exception is None) and (self.status in xrange(200, 400))


class BrokenLinkScanner(object):
    def __init__(self, start_url, name):
        p = urlparse.urlparse(start_url)
        self.base_url = urlparse.urlunparse(urlparse.ParseResult(
            p.scheme, p.netloc, '', '', '', ''))

        self._fail_count = 0
        self._success_count = 0

        self._name = name
        self._results = anydbm.open(name + '.db', 'c')
        self._queue = anydbm.open(name + '.queue', 'c')

        self._push_task(start_url)

    def run(self):
        print("Running...")
        ## Loop until queue is empty
        while self._queue_length() > 0:
            url, void = self._pop_task()

            ## Process the url, to get status + links
            r = self._process_url(url)

            ## Keep success/failure count
            if r.ok:
                self._success_count += 1
            else:
                self._fail_count += 1

            ## Store in database
            dbrec = {
                'url': r.url,
                'headers': dict(r.headers.iteritems()),
                'links': list(r.links),
                'status': r.status,
                'exception': str(r.exception),
            }
            self._results[url] = json.dumps(dbrec)
            self._results.sync()

            ## Add links to queue
            for link in r.links:
                if link not in self._results:
                    self._push_task(link)

            ## Print a status line
            self._print_status(url, r.status)

        ## Print a "done" message upon completion
        self._print_done()

    def _queue_length(self):
        return len(self._queue)

    def _pop_task(self):
        return self._queue.popitem()

    def _push_task(self, name, task=None):
        self._queue[name] = task

    def _process_url(self, url):
        if url.split(':', 1)[0] not in ('http', 'https'):
            return ResultRecord(
                url=url, exception=ValueError("Invalid url"))

        try:
            if url.startswith(self.base_url):
                return self._process_internal(url)
            else:
                return self._process_external(url)
        except Exception, e:
            traceback.print_exc()
            print("\n")
            return ResultRecord(url=url, exception=e)

    def _process_internal(self, url):
        response = requests.get(url)

        links = []
        if response.ok:
            tree = lxml.html.fromstring(response.content)
            links = set()
            for href in tree.xpath('//a/@href'):
                href = href.split('#', 1)[0]
                links.add(urlparse.urljoin(self.base_url, href))

        return ResultRecord(
            url=url,
            links=links,
            status=response.status_code,
            headers=response.headers,
            exception=None)

    def _process_external(self, url):
        ## issue a GET, but we only want headers..
        response = requests.get(url, stream=True)
        return ResultRecord(
            url=url,
            status=response.status_code,
            headers=response.headers,
            exception=None)

    def _print_status(self, url, status):
        sys.stdout.write("\x1b[A\x1b[K")  # Up one line and clear

        if status in xrange(200, 300):
            sys.stderr.write("\x1b[1;32m")
        elif status in xrange(300, 400):
            sys.stderr.write("\x1b[1;33m")
        else:
            sys.stderr.write("\x1b[1;31m")
        print("{0}\x1b[0m {1}".format(status, url))

        ## Print the status line
        succ = self._success_count
        fail = self._fail_count
        tot = len(self._results)
        pending = len(self._queue)
        succ_pc = (succ * 100 / tot) if tot else 'N/A'
        fail_pc = (fail * 100 / tot) if tot else 'N/A'
        try:
            tot_pc = (tot * 100 / (tot + pending))
        except ZeroDivisionError:
            tot_pc = 'N/A'
        print("[ {B}Processed:{E} {tot} ({tot_pc}%)  "
              "{B}Success:{E} {succ} ({succ_pc}%)  "
              "{B}Failed:{E} {fail} ({fail_pc}%)  "
              "{B}Pending:{E} {pending} ]".format(
                  succ=succ, fail=fail, tot=tot,
                  succ_pc=succ_pc, fail_pc=fail_pc, tot_pc=tot_pc,
                  pending=pending, B="\x1b[36m", E="\x1b[0m"))

    def _print_done(self):
        sys.stdout.write("\x1b[K")
        print("Done. {0} URLs processed".format(
            len(self._results)))


if len(sys.argv) != 3:
    print("Usage: find_broken_links.py <url> <name>")
    print("<name> will be used as prefix for support databases")
    sys.exit(2)

start_url = sys.argv[1]
name = sys.argv[2]

bls = BrokenLinkScanner(start_url, name)
bls.run()

print("-" * 80)
print("Processed {0} pages".format(len(bls._results)))

pages_per_code = defaultdict(list)
for url, data in bls._results.iteritems():
    pages_per_code[data.status].append(url)

for code, urls in pages_per_code.iteritems():
    print("Links returning {0}: {1}".format(code, len(urls)))
    # if code != 200:
    #     for url in urls:
    #         print("    - " + url)
print("")

# todo: list pages containing broken links
