#!/usr/bin/env python3
import re
import os
import argparse
import logging
import html.parser
import urllib.request

logger = logging.getLogger("pepperoni")
logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO"))

parser = argparse.ArgumentParser(
    description="Query URL for content",
    formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog="""examples:
    > %(prog)s "https://docs.python.org"
    > %(prog)s "https://docs.python.org" -s ".document h1"
    > %(prog)s "https://docs.python.org" -r "Python ([0-9.]+)\"""",
)
parser.add_argument("url", help="an url to request")
parser.add_argument(
    "-q",
    dest="query",
    metavar="SELECTOR",
    type=str,
    help="a CSS-like selector to query (supports `tag`, `.class` and `#id`)",
)
parser.add_argument(
    "-r", dest="regex", metavar="REGEX", type=re.compile, help="a regular expression",
)


def get_selector(s):
    if s.startswith("#"):
        return lambda tag, attrs: any(
            name == "id" and s[1:] == value for (name, value) in attrs
        )

    if s.startswith("."):
        return lambda tag, attrs: any(
            name == "class" and s[1:] in value.split(" ") for (name, value) in attrs
        )

    return lambda tag, attrs: s == tag


class HTMLParser(html.parser.HTMLParser):
    def __init__(self, query, regex, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._all_selectors = [get_selector(s) for s in query.split(" ") if s]
        self._selector_cursor = 0
        self._stack = []

        self._regex = regex

        self.match = None

    def reset(self):
        self._stack = []
        self._selector_cursor = 0

        super().reset()

    def handle_starttag(self, tag, attrs):
        if len(self._all_selectors) > self._selector_cursor:
            fn = self._all_selectors[self._selector_cursor]

            if fn(tag, attrs):
                self._stack.append(self._selector_cursor)
                self._selector_cursor += 1
            else:
                self._stack.append(None)
        else:
            self._stack.append(None)

    def handle_endtag(self, tag):
        if self._stack.pop() is not None:
            self._selector_cursor -= 1

    def handle_data(self, data):
        if (self.match is None) and len(self._all_selectors) == self._selector_cursor:
            if self._regex:
                regex_match = re.search(self._regex, data)
                if regex_match:
                    self.match = regex_match.group(0)
            else:
                self.match = data


def main():
    args = parser.parse_args()
    logger.debug(args)

    response = urllib.request.urlopen(args.url)

    if response.status != 200:
        print(response.status, response.reason)
        return

    data1 = response.read().decode("utf-8")

    result = ""

    if args.query:
        html_parser = HTMLParser(query=args.query, regex=args.regex)
        html_parser.feed(data1)
        result = html_parser.match
    elif args.regex:
        match = re.search(args.regex, data1)
        if match:
            result = match.group(0)

    print(result or "no matches")


if __name__ == "__main__":
    main()
