#!/usr/bin/env python

# ovh_ssh: manage your ovh ssh keys
# inspired by https://github.com/gheesh/ansible-ovh-dns/

DOCUMENTATION = '''
---
module: ovh_ssh
author: Clement Laforet
short_description: Manage your ssh public keys on OVH via the provided API
description:
    - Manage OVH SSH keys
requirements: [ "ovh" ]
options:
    path:
        required: false
        description:
            - Path to ssh public key
    name:
        required: true
        description:
            - Name of the ssh public key
    state:
        required: false
        default: present
        choices: ['present', 'absent']
        description:
            - Determines wether the ssh is to be created/modified or deleted
              Warning: modification is a delete/create sequence

    default:
        required: false
        default: false
        description:
            - Set ssh key as default
    region:
        required: false
        default: ovh-eu
        description:
            - Region/endpoint to put you ssh keys. Please refer to OVH API documentation
    application_key:
        required: false
        default: false
        description:
            - your application key
    application_secret:
        required: false
        default: false
        description:
            - you application secret
    consumer_key:
        required: false
        default: false
        description:
            - your consumer key
'''

EXAMPLES = '''
# Add or update my_shiny_key
- ovh_ssh: state=present name=my_shiny_key path=/home/user/.ssh/id_dsa.pub
# Remove my_shiny_key
- ovh_ssh: state=absent name=my_shiny_key
'''

import os
import time
import syslog
import sys

try:
    import ovh
except ImportError:
    print "failed=True msg='ovh required for this module'"
    sys.exit(1)


def get_and_compare(module, client, name, key):
    resp = None
    try:
        resp = client.get('/me/sshKey/{}'.format(name))
    except ovh.ResourceNotFoundError:
        return "NotExists"
    except:
        e = sys.exc_info()[0]
        module.fail_json(msg="Unknown API Error: ' {}".format(e))
    ovh_key = resp['key']
    if ovh_key == key:
        return "Ok"
    return "ToUpdate"

OVH_CLIENT_ARGS = [
    "endpoint",
    "application_key",
    "application_secret",
    "consumer_key"
]
def main():

    module = AnsibleModule(
        argument_spec=dict(
            path=dict(default=None),
            name=dict(required=True),
            state=dict(default='present', choices=['present', 'absent']),
            default=dict(default=None),
            endpoint=dict(default=None,aliases=['region']),
            application_key=dict(default=None),
            application_secret=dict(default=None),
            consumer_key=dict(default=None)
        )
    )
    connect_info=dict()
    key_info=None
    # Set params
    ssh_key_file = module.params.get('path')
    ssh_key_name = module.params.get('name')
    key_state = module.params.get('state')
    isDefault = module.params.get('default')
    ovh_endpoint = module.params.get('region')
    ssh_key = None

    for arg in OVH_CLIENT_ARGS:
        connect_info[arg] = module.params.get(arg)
    try:
        client = ovh.Client(**connect_info)
    except:
        e = sys.exc_info()[0]
        module.fail_json(msg="Can't connect to API: ' {}".format(e))

    try:
        key_info = client.get('/me/sshKey/{}'.format(ssh_key_name))
    except ovh.ResourceNotFoundError:
        key_info= {'key': None, 'sshKey': None, 'default':None}
    except:
        e = sys.exc_info()[0]
        module.fail_json(msg="Unable to fetch key {0}: Unknown API Error: ' {1}".format(ssh_key_namessh_key_name,e))

    if key_state == "absent":
        if key_info['key'] == None:
            module.exit_json(changed=False)
        try:
            client.delete('/me/sshKey/{}'.format(ssh_key_name))
        except:
            e = sys.exc_info()[0]
            module.fail_json(msg='delete fail {}'.format(e))
        module.exit_json(changed=True)

    if key_state == "present":
        change=False
        if ssh_key_file is None:
            module.fail_json(msg='Missing path argument')
        try:
            with open(ssh_key_file, "r") as f:
                ssh_key = f.read().replace("\n", '')
        except IOError as e:
            module.fail_json(msg='I/O error({0}):{1}'.format(
                                                        e.errno,
                                                        e.strerror))
        except:
            module.fail_json(msg='Unknow error({0}):{1}'.format(
                                                        e.errno,
                                                        e.strerror))

        if key_info['key'] == ssh_key and key_info['default'] == isDefault and key_info['keyName'] == ssh_key_name:
            module.exit_json(change=False)

        if key_info['default'] is not None and key_info['key'] == ssh_key and isDefault is not None:
            try:
                client.put('/me/sshKey/{}'.format(ssh_key_name),default=isDefault)
            except:
                e = sys.exc_info()[0]
                module.fail_json(msg='put failed {}'.format(e))
            module.exit_json(msg="key updated", changed=True)

        if key_info['default'] is not None:
            try:
                client.delete('/me/sshKey/{}'.format(ssh_key_name))
            except:
                e = sys.exc_info()[0]
                module.fail_json(msg='delete failed {}'.format(e))
        try:
            client.post("/me/sshKey", key=ssh_key, keyName=ssh_key_name)
        except:
            e = sys.exc_info()[0]
            module.fail_json(msg='post fail {}'.format(e))
        isDefault = isDefault if isDefault is not None else key_info["default"]
        if isDefault is not None:
            try:
                client.put('/me/sshKey/{}'.format(ssh_key_name),default=isDefault)
            except:
                e = sys.exc_info()[0]
                module.fail_json(msg='update default failed - inconsistency may happen {}'.format(e))
        module.exit_json(changed=True)

    module.fail_json(msg="you shouln't be here !")

# import module snippets
from ansible.module_utils.basic import *
main()
