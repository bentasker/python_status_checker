#!/usr/bin/env python3
#
# Prefect flow to perform HTTP reachability checks against URLs
# Designed to be run from something like a Github Action
#
# Copyright (c) 2023, B Tasker
# Released under BSD 3-Clause License
#
# pip install requests httpx[http2] prefect influxdb-client
# ./status-check.py "$influx_token", "$influx_bucket", "$influx_url"
#
'''
Copyright (c) 2023, B Tasker

All rights reserved.

Redistribution and use in source and binary forms, with or without modification, are
permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this list of
conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice, this list of
conditions and the following disclaimer in the documentation and/or other materials
provided with the distribution.

3. Neither the name of the copyright holder nor the names of its contributors may be used
to endorse or promote products derived from this software without specific prior written
permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY
EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR
TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
'''

import httpx
import logging
import requests
import re
import sys
import time

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
#from prefect import flow, task, get_run_logger
#from prefect.events import emit_event
from requests.adapters import HTTPAdapter


# Define the URLs to check and the protocols that should be checked
urls = [
   { "url": "https://mastodon.bentasker.co.uk/", "check" : ["h1", "h2"] },
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
    #logger = get_run_logger()
    logger = logging
    if level == "warn":
        logger.warn(f"{check}: {message}")
    else:
        logger.info(f"{check}: {message}")


def sendEvent(check, state, url, result):
    ''' Send a Prefect event
    
    '''
    slugify_url = re.sub(r'\W+', '-', url)
    emit_event(
            event=f"{check}.status.{state}", 
            resource={"prefect.resource.id": f"{check}.{slugify_url}"},
            payload={
                "url" : url, 
                #"http_status" : result['status_code'],
                "http_status" : f"418 (real: {result['status_code']}",
                "reason" : f"I'm a teapot.... {result['failure_reason']}"
                }
        )       

def emit_event(event, resource, payload):
    print(f"{event}: {resource} {payload}")
    

#@task
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
        res = False
    
    result = process_result(res, url_result, failed, start, stop)
    
    
    
    if result['status'] == 1:
        do_log("http1", f"{url} is UP")
        sendEvent("h1", "UP", url, result)
                
    else:
        do_log("http1", f"{url} is DOWN. Reason {result['failure_reason']}")
        sendEvent("h1", "DOWN", url, result)        
  
        
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
    
#@task    
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
    slugify_url = re.sub(r'\W+', '-', url)
    
    if result['status'] == 1:
        do_log("http2", f"{url} is UP")
        sendEvent("h2", "UP", url, result)
    else:
        do_log("http2", f"{url} is DOWN. Reason {result['failure_reason']}")
        sendEvent("h2", "DOWN", url, result)

    return result


        
#@flow    
def main(check_urls):
    ''' Main entry point
    
    Iterate through the configured URLs and send configured probes
    '''
    results = []
    res = []
    for url in check_urls:
        if "h1" in url['check']:
            res.append(do_h1_check(url['url']))

        if "h2" in url['check']:
            res.append(do_h2_check(url['url']))
    
    # We ran tasks concurrently so results currently just contains
    # a bunch of prefect futures
    #
    # We need to iterate through calling results() on each of them 
    # to get the result dicts 

    #for prefectfuture in results:
    #    res.append(prefectfuture.result())
    
    print(res)
    if len(res) < 1:
        return
    
    # Otherwise, time to write the stats out
    token = sys.argv[1]
    bucket = sys.argv[2]
    influx_url = sys.argv[3]
    
    client = InfluxDBClient(url=influx_url, token=token, org="")
    write_api = client.write_api(write_options=SYNCHRONOUS)
    
    points = []
    for r in res:
        points.append(build_point(r))
    
    write_api.write(bucket, "", points)
    
    
def build_point(rdict):
    ''' Accept a result dict and turn it into an InfluxDB point
    '''
    p = Point("http_reachability_check")
    p.tag("http_version", rdict['http_version'])
    p.tag("url", rdict['url'])
    p.tag("failure_reason", rdict['failure_reason'])
    
    if rdict["status"] == 0:
        p.tag("result", "failed")
    else:
        p.tag("result", "success")
        
    p.field("probe_status", rdict["status"])
    p.field("request_duration", rdict["request_duration_ns"])
    p.field("http_status", rdict["status_code"])
    p.field("bytes_transferred", rdict["bytes_transferred"])
    
    p.time(rdict['request_timestamp_ns'])
    return p
    

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
