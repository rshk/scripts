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


DEBUG = False  # Print debug messages

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

        self._push_task(start_url, trail=[])

    def run(self):
        """Continue processing tasks until queue is empty"""

        print("Running...")

        while self._queue_length() > 0:
            ## Get a task from the queue
            url, current_task = self._pop_task()

            ## Process the url, to get status + links
            self._debug("Processing: " + url)
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
            self._store(r.url, dbrec)

            ## Add links to queue
            for link in r.links:
                trail = []
                if 'trail' in current_task:
                    trail.extend(current_task['trail'])
                trail.append(url)
                self._push_task(link, trail=trail)

            ## Print a status line
            self._print_status(url, r)

        ## Print a "done" message upon completion
        self._print_done()

    def _debug(self, msg):
        if DEBUG:
            print(msg, file=sys.stderr)

    def _store(self, name, value):
        self._results[name.encode('utf-8')] = \
            json.dumps(value).encode('utf-8')
        self._results.sync()

    def _queue_length(self):
        return len(self._queue)

    def _pop_task(self):
        k, v = self._queue.popitem()
        v = json.loads(v)
        return k, v

    def _push_task(self, name, **task):
        self._debug("Push task: {0!r} {1!r}".format(name, task))
        name = name.encode('utf-8')
        if not self._should_follow(name, task):
            return
        task = json.dumps(task).encode('utf-8')
        self._queue[name] = task

    def _should_follow(self, url, task):
        """
        Decide whether we should follow an url, executing a task.
        """

        ## We already run this task
        if url in self._results:
            self._debug("Skipping task {0}: already run".format(url))
            return False

        ## We only support http(s):// URLs right now
        if url.split(':', 1)[0] not in ('http', 'https'):
            self._debug("Skipping task {0}: unsupported scheme".format(url))
            return False

        ## we need to find a way to avoid ending up following endless
        ## paths, such as facet links in filtering forms.
        ## Best way would be to detect such URLs, but for now, we just
        ## limit the maximum trail length to 5.
        if 'trail' in task and len(task['trail']) >= 5:
            self._debug("Skipping task {0}: trail length exceeded".format(url))
            return False

        return True

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
        """
        For internal links, we also want to extract all the href links
        """
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
        """
        For external URLs, we don't extract links, so we are only
        interested in status + headers.
        """
        ## issue a GET, but we only want headers..
        response = requests.get(url, stream=True)
        return ResultRecord(
            url=url,
            status=response.status_code,
            headers=response.headers,
            exception=None)

    def _print_status(self, url, response):
        ## Do the calculations first, to prevent flickering
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

        ## (Up one line, blank line) * 2
        sys.stdout.write("\x1b[A\x1b[K" * 2)

        ## Print URL + status
        status = response.status
        if status in xrange(200, 300):
            sys.stderr.write("\x1b[1;32m")
        elif status in xrange(300, 400):
            sys.stderr.write("\x1b[1;33m")
        else:
            sys.stderr.write("\x1b[1;31m")
        print("{0}\x1b[0m {1} \x1b[36m({2})\x1b[0m\n".format(
            status, url, response.headers.get('Content-type', '???')))

        ## Print the status line, with counters
        print("[ {B}Processed:{X} {tot} ({tot_pc}%)  "
              "{G}Success:{X} {succ} ({succ_pc}%)  "
              "{R}Failed:{X} {fail} ({fail_pc}%)  "
              "{B}Pending:{X} {pending} ]".format(
                  succ=succ, fail=fail, tot=tot,
                  succ_pc=succ_pc, fail_pc=fail_pc, tot_pc=tot_pc,
                  pending=pending, B="\x1b[36m", X="\x1b[0m",
                  G="\x1b[32m", R="\x1b[31m"))

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
    try:
        data = json.loads(data)
    except ValueError:
        pass
    else:
        pages_per_code[data['status']].append(url)

for code, urls in pages_per_code.iteritems():
    print("Links returning {0}: {1}".format(code, len(urls)))
    # if code != 200:
    #     for url in urls:
    #         print("    - " + url)
print("")

# todo: list pages containing broken links
