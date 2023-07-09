#!/usr/bin/env python3
#
#
#

import requests
import time

from requests.adapters import HTTPAdapter


urls = [
   { "url": "https://mastodon.bentasker.co.uk/", "check" : ["h1"] },
   { "url": "https://www.bentasker.co.uk/", "check" : ["h1"] }
]



def do_check(url):
    ''' Send a probe to the URL and record specifics about it
    
    '''
    url_result = {
        "url" : url,
        "http_version" : "1.1"
        "status" : "0", # 0 - down, 1 - up
        "failure_reason" :  "nofail",
        "request_duration_ns" : 0,
        "status_code" : 0,
        "bytes_transferred" : 0
        }

    headers = {}
    failed = False
    try:
        # We don't want any retries - it should fail first time 
        #
        s = requests.Session()
        s.mount('http', HTTPAdapter(max_retries=0))

        start = time.time_ns()
        res = s.get(url, headers=headers, 
                           timeout=(5, 5) # 5 second timeout for connect, another 5 for read
                           )
        stop = time.time_ns()

    except Exception as e:
        stop = time.time_ns()
        print(f"aaaaa {e}")
        url_result["failure_reason"] = match_exception_string(str(e).lower())
        failed = True
    
    # Calculate the timings
    url_result['request_duration_ns'] = stop - start
    
    # Note the timestamp of the request
    url_result['request_timestamp_ns'] = start
    
    # If the request failed, we can't really go any further
    if failed:
        return url_result
    
    # Otherwise, update status code and response body size etc
    url_result['status_code'] = res.status_code
    
    if "Content-Length" in res.headers:
        url_result['bytes_transferred'] = int(res.headers["Content-Length"])
    else:
        # This isn't technically accurate - if the response was non-ascii
        # one char may not == 1 byte.
        #
        # However, this shouldn't matter too much as we're only really looking
        # for consistency between responses
        url_result['bytes_transferred'] = len(res.text)
    
    return url_result
    
    
def main(check_urls):
    # iterate through the urls
    for url in check_urls:
        if "h1" in url['check']:
            http1_result = do_check(url['url'])
            print(http1_result)


def match_exception_string(s):
    ''' Take an exception string and check for certain 
    known values so we can report the reason for failure
    in a controlled manner
    '''
    pairs = [
        ["name or service not known", "dns-nxdomain"],
        ["timed out", "timeout"],
        ["connectionrefused", "conn-refused"],
        ["closed connection without response", "conn-close"],
        ["caused by sslerror", "tls-error"]
    ]
    
    for pair in pairs:
        if pair[0] in s:
            return pair[1]
    
    return "unknown"
    
    


main(urls)

