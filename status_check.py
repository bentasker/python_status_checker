#!/usr/bin/env python3
#
# pip install requests httpx[http2] prefect
#
import httpx
import requests
import time

from prefect import flow, task, get_run_logger
from requests.adapters import HTTPAdapter


# Define the URLs to check and the protocols that should be checked
urls = [
   { "url": "https://mastodon.bentasker.co.uk/", "check" : ["h1"] },
   { "url": "https://www.bentasker.co.uk/", "check" : ["h1", "h2"] }
]


VERSION = "0.1"

def get_check_dict(url):
    ''' Generate the dict used to record HTTP probe
        responses
        
    '''
    return {
        "url" : url,
        "http_version" : "1.1",
        "status" : "0", # 0 - down, 1 - up
        "failure_reason" :  "nofail",
        "request_duration_ns" : 0,
        "status_code" : 0,
        "bytes_transferred" : 0
    } 


def get_request_headers():
    ''' Return a dict of request headers to pass into a request
    
    '''
    return {"User-agent": f"Ben's status-checker {VERSION}" }

def do_log(check, message, level="info"):
    ''' Write out a log line
    '''
    logger = get_run_logger()
    if level == "warn":
        logger.warn(f"{check}: {message}")
    else:
        logger.info(f"{check}: {message}")

@task
def do_h1_check(url):
    ''' Send a HTTP/1.1 probe to the URL and record specifics about it
    '''
    url_result = get_check_dict(url)
    headers = get_request_headers()
    failed = False
    do_log("http1", f"Starting HTTP/1.1 check for {url}")
    
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
        # Trap exceptions and attempt to provide a normalised string identifying
        # the cause of the failure
        stop = time.time_ns()
        url_result["failure_reason"] = match_exception_string(str(e).lower())
        do_log("http1", f"HTTP/1.1 check for {url} resulted in exception: {e}", "warn")
        failed = True
    
    result = process_result(res, url_result, failed, start, stop)
    
    if result['status'] == 1:
        do_log("http1", f"{url} is UP")
    else:
        do_log("http1", f"{url} is DOWN. Reason {result['failure_reason']}")
        
    return result
    
def process_result(res, url_result, failed, start, stop):
    ''' Populate the result dict 
    
        res should be a requests compatible object
    '''
    # Calculate the timings
    url_result['request_duration_ns'] = stop - start
    
    # Note the timestamp of the request
    url_result['request_timestamp_ns'] = start
    
    # If the request failed, we can't really go any further
    if failed:
        return url_result
    
    # Record the status code and check whether it indicates success
    url_result['status_code'] = res.status_code
    if res.status_code < 200 or res.status_code >= 300:
        url_result['status'] = 0
        url_result["failure_reason"] = "status-code"
    else:
        url_result['status'] = 1
    
    # Extract or calculate response body length
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
    
@task    
def do_h2_check(url):
    ''' Send a HTTP/2 probe to the URL and build
    a results dict
    '''
    url_result = get_check_dict(url)
    headers = get_request_headers()
    failed = False
    url_result["http_version"] = "2"
    do_log("http2", f"Starting HTTP/2 check for {url}")    
    
    try:
        start = time.time_ns()
        client = httpx.Client(http2=True, headers=headers)
        res = client.get(url)
        stop = time.time_ns()
    except Exception as e:
        stop = time.time_ns()
        url_result["failure_reason"] = match_exception_string(str(e).lower())
        do_log("http2", f"HTTP/2 check for {url} resulted in exception: {e}", "warn")        
        failed = True
        # If we failed to connect, res won't exist
        # prevent exceptions
        res = False
        
    if not failed and res.http_version != "HTTP/2":
        # Although we might have got a response it wasn't H2
        # so it's a fail
        url_result['status'] = 0
        url_result["failure_reason"] = "not-http2"
        failed = True
        
    result = process_result(res, url_result, failed, start, stop)
    
    if result['status'] == 1:
        do_log("http2", f"{url} is UP")
    else:
        do_log("http2", f"{url} is DOWN. Reason {result['failure_reason']}")
        
    return result


        
@flow    
def main(check_urls):
    ''' Main entry point
    
    Iterate through the configured URLs and send configured probes
    '''
    results = []
    for url in check_urls:
        if "h1" in url['check']:
            results.append(do_h1_check.submit(url['url']))

        if "h2" in url['check']:
            results.append(do_h2_check.submit(url['url']))
    
    # We ran tasks concurrently so results currently just contains
    # a bunch of prefect futures
    #
    # We need to iterate through calling results() on each of them 
    # to get the result dicts 
    res = []
    for prefectfuture in results:
        res.append(prefectfuture.result())
    
    print(res)


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
    
    

if __name__ == "__main__":
    main(urls)
