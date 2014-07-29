# -*- coding: utf-8 -*-
#
# Copyright (C) 2014 Max Kaskevich <maxim.kaskevich@gmail.com>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution.

import socket
import httplib
import json
import urllib
from datetime import datetime
import time
import re

from tools import Singleton

class BuildbotException(Exception):
    def __init__(self, args):
        Exception.__init__(self, args)

class BuildbotConnection(Singleton):
    headers = {'connection': 'Keep-Alive',
               'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'}
    user=""
    password=""
    max_request_try = 2

    def __init__(self, url=None):
        if url:
            self.connect_to(url)
        else:
            self.url = ""
            self.connection = None

    def connect_to(self, url):
        if not hasattr(self,'url') or self.url != url:
            self.url = url
            self.reconnect()

    def reconnect(self):
        match = re.match("(.*)://(.*)", self.url)
        if match:
            protocol, server = match.groups()
            if protocol == "http":
                self.connection = httplib.HTTPConnection(server)
            elif protocol == "https":
                self.connection = httplib.HTTPSConnection(server)
            else:
                raise BuildbotException("Request failed - unknown protocol")

    def _request(self, request_msg, method="GET", **kwagrs):
        if not self.connection:
            raise BuildbotException("Request failed - connection not initialized")

        request_msg = urllib.quote(request_msg)

        if kwagrs:
            kwagrs = urllib.urlencode(kwagrs)
        else:
            kwagrs = None
        
        request_try = 0
        while(request_try < self.max_request_try):
            request_try += 1
            r = None
            try:
                self.connection.request(method, request_msg, kwagrs, self.headers)
                r = self.connection.getresponse()

            except (socket.error, httplib.CannotSendRequest, httplib.ResponseNotReady) as e:
                if not request_try < self.max_request_try:
                    raise BuildbotException("Request %s failed %s: %s" % (request_msg, "%s.%s" % (e.__module__, type(e).__name__), e))
                else:
                    time.sleep(1)
                    self.reconnect()
                    continue

            if not (200 <= r.status < 400):
                if not request_try < self.max_request_try:
                    raise BuildbotException("Request %s failed (%s %s)" % (request_msg, r.status, r.reason))
                else:
                    time.sleep(1)
                    self.reconnect()
                    continue
            else:
                break

        return r

    def get_builders(self):
        res = self._request('/json/builders')
        return [name for name in json.loads(res.read())]

    def login(self, user, password):
        r = self._request("/login", "POST", username=user, passwd=password)
        r.read()
        cookie = r.getheader('set-cookie')
        if not cookie:
            return False
        self.headers['cookie'] = cookie # yam yam, tasty cookie
        self.user = user
        self.password = password
        return True

    def build(self, builder):
        r = self._request("/builders/%s/force" % builder, method="POST",
                              reason='launched from trac', forcescheduler='force')
        r.read()
        #if r.read().find('authfail'):
        #    if not self.login(self.user, self.password):
        #        raise BuildbotException('Authorization failed')
        #    r = self._raw_request("/builders/%s/force" % builder, method="POST",
        #                          reason='launched from trac', forcescheduler='force')

    def _parse_build(self, res):
        data = json.loads(res.read())

        if not 'results' in data or not (type(data['results']) == int):
            status = "running"
        else:
            status = "successful" if data['results'] == 0 else "failed"

        build = dict({
                'builder': data['builderName'],
                'status': status,
                'start' : datetime.fromtimestamp(int(data['times'][0])),
                'num': data['number'],
                })

        if len(data['times']) > 1 and type(data['times'][1]) == float:
            build['finish'] = datetime.fromtimestamp(int(data['times'][1]))

        for prop in data['properties']:
            if prop[0] == 'got_revision' and prop[1] != "":
                build["rev"] = prop[1]
                break

        if status == "failed":
            build['error'] = ', '.join(data['text'])
            try:
                for step in data['steps']:
                    if "results" in step and step["results"][0] == 2:
                        build['error_log'] = step['logs'][0][1]
                        break
            except (IndexError, KeyError):
                pass

        return build

    def get_build(self, builder, num):
        res = self._request("/json/builders/%s/builds/%d" % (builder, num))
        return self._parse_build(res)


if __name__ == "__main__":
    bc = BuildbotConnection()
    bc.connect_to("localhost:8010")
    builders = bc.get_builders()
    print("BUILDERS:", [name for name in builders],"\n")

    #print "LAST BUILDS:",bc.get_last_builds(builders),"\n"
    print("LAST BUILDS:")
    for name, builder in bc.get_last_builds(builders).iteritems():
        last_build = builder['builds']['-1']  
        print(name, ":")
        print("build " + ( "successful " if last_build['results'] == 0 else "failed (%s)" % last_build['results']))
        print("started at", datetime.datetime.fromtimestamp(last_build['times'][0]))
        print("finished at", datetime.datetime.fromtimestamp(last_build['times'][1]))
        print("buildnumber - ", last_build['number'])

        for prop in  last_build['properties']:
            if prop[0] == 'got_revision':
                print("revision - ", prop[1])
                break
        print("")

    #print "BUILD TEST:"
    #try:
    #    bc.build('runtests')
    #except buildbot_api.BuildbotException as e:
    #    print (e)


    print("LOGIN TEST:")
    print(bc.login("qwe","qwe"))

    #print "BUILD TEST:"
    #print (bc.build('runtests'))


