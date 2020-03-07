#!/usr/bin/env python3

# spices
import os
import time
import platform

# sause
import re
import difflib
import textwrap
import html.parser

# meat
import urllib.request

# dough
import logging
import argparse

parser = argparse.ArgumentParser(
    description="Query URL for content",
    formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog=textwrap.dedent(
        """
        examples:
          > %(prog)s "https://docs.python.org" -q ".document h1"
          > %(prog)s "https://docs.python.org" -r "Python ([0-9.]+)"
          > %(prog)s "https://time.is" -w -u -i 5
          > %(prog)s "https://time.is" -q time -i 5
        """
    ),
)
parser.add_argument("url", help="an url to request")
parser.add_argument(
    "--whole",
    "-w",
    default=False,
    action="store_true",
    help="match whole response body (ignore -q and -r arguments)",
)
parser.add_argument(
    "--query",
    "-q",
    metavar="SELECTOR",
    type=str,
    help="a CSS-like selector to query (supports `tag`, `.class` and `#id`)",
)
parser.add_argument(
    "--regex", "-r", metavar="REGEX", type=re.compile, help="a regular expression",
)
parser.add_argument(
    "--interval", "-i", metavar="SECONDS", type=int, help="interval between queries",
)
parser.add_argument(
    "--until-change",
    "-u",
    default=False,
    action="store_true",
    help="retry until match is changed, then exit",
)

if platform.system() == "Darwin":
    parser.add_argument(
        "--sound",
        "-s",
        dest="mac_sound",
        default="pop",
        # `ls /System/Library/Sounds/`
        choices=[
            "basso",
            "blow",
            "bottle",
            "frog",
            "funk",
            "glass",
            "hero",
            "morse",
            "ping",
            "pop",
            "purr",
            "sosumi",
            "submarine",
            "tink",
        ],
        type=str,
        help="sound to play (macOS only)",
    )

parser.add_argument("--verbose", "-v", action="count", default=0, help="verbose output")


def get_selector(s):
    """
    >>> tag_selector = get_selector("h1")
    >>> tag_selector("div", [])
    False
    >>> tag_selector("h1", [])
    True

    >>> id_selector = get_selector("#uniq")
    >>> id_selector("div", [("class", "cls")])
    False
    >>> id_selector("div", [("id", "")])
    False
    >>> id_selector("div", [("id", "uniq")])
    True

    >>> class_selector = get_selector(".cls")
    >>> class_selector("div", [("id", "uniq")])
    False
    >>> class_selector("div", [("class", "")])
    False
    >>> class_selector("div", [("class", "xxcls")])
    False
    >>> class_selector("div", [("class", "cls")])
    True
    >>> class_selector("div", [("class", "cls another")])
    True
    """
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


def query_html(html, query, regex):
    """
    >>> html = "<ul><li>A</li><li id='b'>B</li></ul><ol><li>C</li><li class='d'>D</li></ol>"
    >>> query_html(html, "li", None)
    'A'
    >>> query_html(html, "#b", None)
    'B'
    >>> query_html(html, "ol li", None)
    'C'
    >>> query_html(html, ".d", None)
    'D'
    >>> query_html(html, "ul li", "B|X")
    'B'
    >>> query_html(html, "ol li", "B|X")
    """
    if query:
        html_parser = HTMLParser(query, regex)
        html_parser.feed(html)
        return html_parser.match
    elif regex:
        match = re.search(regex, html)
        if match:
            return match.group(0)

    return None


def request_and_query(url, whole, query, regex):
    response = urllib.request.urlopen(
        urllib.request.Request(
            url, headers={"Accept": "text/html", "User-Agent": "Mozilla/5.0"}
        )
    )

    if response.status != 200:
        logging.warning(response.status, response.reason)
        return None

    response_body = response.read().decode("utf-8")

    if whole:
        return response_body

    return query_html(response_body, query, regex)


def pepperoni(url, whole, query, regex, interval, until_change, mac_sound, **kwargs):
    result = request_and_query(url, whole, query, regex)

    if result is None:
        logging.warning("no matches")
    elif until_change and whole:
        logging.info("%s bytes", len(result))
    else:
        logging.info(result)

    while interval is not None:
        logging.debug("doing to sleep for %s seconds", interval)
        time.sleep(interval)

        prev = result
        result = request_and_query(url, whole, query, regex)

        if result is None:
            logging.warning("no matches")
        elif until_change and whole:
            logging.info("%s bytes", len(result))
        else:
            logging.info(result)

        if prev != result:
            if mac_sound:
                os.system(
                    f"afplay /System/Library/Sounds/{mac_sound.title()}.aiff 2> /dev/null"
                )
            else:
                print("\a", end="", flush=True)

            if whole and prev and result:
                d = difflib.Differ()

                logging.info(
                    "\n".join(
                        difflib.unified_diff(
                            textwrap.wrap(prev), textwrap.wrap(result), lineterm="", n=1
                        )
                    )
                )

            if until_change:
                break


if __name__ == "__main__":
    args = parser.parse_args()

    logFormat = ""
    if args.verbose:
        logFormat = "%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s"

    logLevel = logging.INFO
    if args.verbose >= 2:
        logLevel = logging.DEBUG

    logging.basicConfig(
        format=logFormat, datefmt="%Y-%m-%dT%H:%M:%S", level=logLevel,
    )

    logging.debug(args)

    pepperoni(**vars(args))
