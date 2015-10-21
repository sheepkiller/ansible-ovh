#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Mostly a copy and paste from cobbler.py
#
# (c) 2012, Michael DeHaan <michael.dehaan@gmail.com> (as cobble.py author)
# (c) 2015, Clement Laforet <clement.laforet@gmail.com> (for ovh support)
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.


import sys
import argparse
import re
import os
import ConfigParser
from time import time

try:
    import json
except ImportError:
    import simplejson as json

# Avoid to load ourself - Doesn't work with symlinks
for path in [os.getcwd(), '', os.path.dirname(os.path.abspath(__file__))]:
    try:
        del sys.path[sys.path.index(path)]
    except:
        pass

try:
    import ovh
except ImportError:
    print "failed=True msg='ovh required for this software'"
    sys.exit(1)

try:
    import ipaddress
except ImportError:
    print "failed=True msg='py2-ipaddress required for this software'"
    sys.exit(1)

def removeKey(d, key):
    if key in d: del d[key]

def cleanUpHost(d):
    for k in d:
        d[k.lower()] = d.pop(k)
    if "ip" in d:
        d['primary_ip'] = d.pop("ip")
    if "reverse" in d:
        d['reverse'] = d['reverse'].rstrip('.')

removeArgsVps = [
    "monitoringIpBlocks",
    "keymap",
    "model"
]

removeArgsServer = [
    "commercialRange",
    "professionalUse",
    "rescueMail",
    "rootDevice",
    "serverId",
    "state",
    "supportLevel",
    "bootId"
]
class OvhInventory(object):

    def __init__(self):

        """ Main execution path """
        self.conn = None

        self.inventory = dict()  # A list of groups and the hosts in that group
        self.cache = dict()  # Details about hosts in the inventory

        # Read settings and parse CLI arguments
        self.read_settings()
        self.parse_cli_args()

        # Cache
        if self.args.refresh_cache:
            self.update_cache()
        elif not self.is_cache_valid():
            self.update_cache()
        else:
            self.load_inventory_from_cache()
            self.load_cache_from_cache()

        data_to_print = ""

        # Data to print
        if self.args.host:
            data_to_print += self.get_host_info()
        else:
            self.inventory['_meta'] = { 'hostvars': {} }
            for hostname in self.cache:
                self.inventory['_meta']['hostvars'][hostname] = self.cache[hostname]
            data_to_print += self.json_format_dict(self.inventory, True)

        print(data_to_print)


    def is_cache_valid(self):
        """ Determines if the cache files have expired, or if it is still valid """

        if os.path.isfile(self.cache_path_cache):
            mod_time = os.path.getmtime(self.cache_path_cache)
            current_time = time()
            if (mod_time + self.cache_max_age) > current_time:
                if os.path.isfile(self.cache_path_inventory):
                    return True

        return False

    def read_settings(self):
        """ Reads the settings from the ovh.ini file """
        pattern = re.compile(r'\s+')
        config = ConfigParser.SafeConfigParser()
        config.read(os.path.dirname(os.path.realpath(__file__)) + '/ovh.ini')
        self.regions = []
        configRegions = re.sub(pattern, '', config.get('ovh', 'regions'))
        self.regions = configRegions.split(",")
        configGroupby = re.sub(pattern, '',config.get('ovh', 'group_by'))
        self.Groupby = configGroupby.split(",")
        self.configHostname = config.get('ovh', 'hostname')


        # Cache related
        cache_path = config.get('ovh', 'cache_path')
        self.cache_path_cache = cache_path + "/ansible-ovh.cache"
        self.cache_path_inventory = cache_path + "/ansible-ovh.index"
        self.cache_max_age = config.getint('ovh', 'cache_max_age')

    def parse_cli_args(self):
        """ Command line argument processing """

        parser = argparse.ArgumentParser(description='Produce an Ansible Inventory file based on OVH')
        parser.add_argument('--list', action='store_true', default=True, help='List instances (default: True)')
        parser.add_argument('--host', action='store', help='Get all the variables about a specific instance')
        parser.add_argument('--refresh-cache', action='store_true', default=False,
                            help='Force refresh of cache by making API requests to ovh (default: False - use cache files)')
        self.args = parser.parse_args()

    def add_to_cache(self, d, type,region):
        d["region"] = region
        d["type"] = type
        cleanUpHost(d)
        host = None
        if self.configHostname == "primary_ip":
            host = d["primary_ip"]
        if self.configHostname == "servicename":
            host = d["name"]
        if self.configHostname == "customname":
            fallback = d["primary_ip"] if "reverse" not in d else d["reverse"]
            host = fallback if "displayname" not in d else d["displayname"]

        self.cache[host] = d
        for gb in self.Groupby:
            if gb in d:
                self.push(self.inventory, d[gb] , host)

    def get_vps(self, region):
        data = self.conn.get('/vps')
        for host in data:
            vps = dict()
            #self.cache[host] = host
            vps = self.conn.get('/vps/{}'.format(host))
            for k in removeArgsVps:
                removeKey(vps, k)
            ips = self.conn.get('/vps/{}/ips'.format(host))
            list_ips=dict()
            for ip in ips:
                ip_info = self.conn.get('/vps/{0}/ips/{1}'.format(host,ip))
                v = ip_info["version"]
                if ip_info["type"] == "primary" and v == "v4":
                    vps["ip"] = ip
                if v not in list_ips:
                    list_ips[v] = []
                list_ips[v].append(ip)

            vps["ips"]=list_ips
            self.add_to_cache(vps, "vps", region)


    def get_dedicated(self, region):
        data = self.conn.get('/dedicated/server')
        for host in data:
            c = dict()
            server = dict()
            #self.cache[host] = host
            server = self.conn.get('/dedicated/server/{}'.format(host))
            c["reverse"] = server["reverse"] if server["reverse"] else server['ip']
            for k in removeArgsServer:
                removeKey(server, k)
            ips = self.conn.get('/dedicated/server/{}/ips'.format(host))
            list_ips = dict()
            for _ip in ips:
                ip = _ip.split('/')[0]
                ip_info = dict()
                v = 'v' + str(ipaddress.ip_address(ip).version).lower()
                if v not in list_ips:
                    list_ips[v] = []
                list_ips[v].append(ip)

            server["ips"]=list_ips
            self.add_to_cache(server, "server", region)

    def update_cache(self):
        """ Make calls to ovh and save the output in a cache """
        self.groups = dict()
        self.hosts = dict()
        for region in self.regions:
            self.conn = ovh.Client(endpoint=region)
            self.get_vps(region)
            self.get_dedicated(region)

        self.write_to_cache(self.cache, self.cache_path_cache)
        self.write_to_cache(self.inventory, self.cache_path_inventory)

    def get_host_info(self):
        """ Get variables about a specific host """

        if not self.cache or len(self.cache) == 0:
            # Need to load index from cache
            self.load_cache_from_cache()

        if not self.args.host in self.cache:
            # try updating the cache
            self.update_cache()

            if not self.args.host in self.cache:
                # host might not exist anymore
                return self.json_format_dict({}, True)

        return self.json_format_dict(self.cache[self.args.host], True)

    def push(self, my_dict, key, element):
        """ Pushed an element onto an array that may not have been defined in the dict """

        if key in my_dict:
            my_dict[key].append(element)
        else:
            my_dict[key] = [element]

    def push_group(self, my_dict, key, element):
        ''' Push a group as a child of another group. '''
        parent_group = my_dict.setdefault(key, {})
        if not isinstance(parent_group, dict):
            parent_group = my_dict[key] = {'hosts': parent_group}
        child_groups = parent_group.setdefault('children', [])
        if element not in child_groups:
            child_groups.append(element)


    def load_inventory_from_cache(self):
        """ Reads the index from the cache file sets self.index """

        cache = open(self.cache_path_inventory, 'r')
        json_inventory = cache.read()
        self.inventory = json.loads(json_inventory)

    def load_cache_from_cache(self):
        """ Reads the cache from the cache file sets self.cache """

        cache = open(self.cache_path_cache, 'r')
        json_cache = cache.read()
        self.cache = json.loads(json_cache)

    def write_to_cache(self, data, filename):
        """ Writes data in JSON format to a file """
        json_data = self.json_format_dict(data, True)
        cache = open(filename, 'w')
        cache.write(json_data)
        cache.close()

    def to_safe(self, word):
        """ Converts 'bad' characters in a string to underscores so they can be used as Ansible groups """

        return re.sub("[^A-Za-z0-9\-]", "_", word)

    def json_format_dict(self, data, pretty=False):
        """ Converts a dict to a JSON object and dumps it as a formatted string """

        if pretty:
            return json.dumps(data, sort_keys=True, indent=2)
        else:
            return json.dumps(data)

OvhInventory()
