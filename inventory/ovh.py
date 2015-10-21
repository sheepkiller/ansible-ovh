#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Mostly a copy and paste from cobbler.py
#

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

try:
    import ovh
except ImportError:
    print "failed=True msg='ovh required for this module'"
#    sys.exit(1)

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

        config = ConfigParser.SafeConfigParser()
        config.read(os.path.dirname(os.path.realpath(__file__)) + '/ovh.ini')
        self.regions = []
        configRegions = config.get('ovh', 'regions')
        self.regions = configRegions.split(",")


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

    def get_vps(self):
        data = self.conn.get('/vps')
        for host in data:
            vps = dict()
            #self.cache[host] = host
            info = self.conn.get('/vps/' + host)
            vps['ovh_name']= host
            vps['zone'] = info['zone']
            ips = self.conn.get('/vps/' + host + '/ips')
            for ip in ips:
                ip_info = self.conn.get('/vps/' + host + '/ips/' + ip)
                key = "ip" + str.join("-", [ip_info["version"]])
            self.cache[host] = vps
            self.push(self.inventory, "vps", host)

    def get_dedicated(self):
        data = self.conn.get('/dedicated/server')
        for host in data:
            c = dict()
            server = dict()
            #self.cache[host] = host
            info = self.conn.get('/dedicated/server/' + host)
            server['ovh_name']= host
            server['datacenter'] = info['datacenter']
            c["ovh_name"] = host
            server["ip"] = c["main_ip"] = info['ip']
            c["reverse"] = info["reverse"] if info["reverse"] else info['ip']
            server["reverse"] = info["reverse"]
            ips = self.conn.get('/dedicated/server/' + host + '/ips')

            self.cache[c["reverse"]] = server
            self.push(self.inventory, "servers", c["reverse"])

    def update_cache(self):
        """ Make calls to ovh and save the output in a cache """
        self.groups = dict()
        self.hosts = dict()
        for region in self.regions:
            self.conn = ovh.Client()
            self.get_vps()
            self.get_dedicated()

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