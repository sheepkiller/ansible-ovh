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
    region:
        required: false
        default: ovh-eu
        description:
            - Region to put you ssh keys. Please refer to OVH API documentation
    makedefault:
        required: false
        default: false
        description:
            - Set default ssh key
              Not yet implemented
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


def main():

    module = AnsibleModule(
        argument_spec=dict(
            path=dict(default=None),
            name=dict(required=True),
            state=dict(default='present', choices=['present', 'absent']),
            region=dict(default="ovh-eu"),
            makedefault=dict(default=False)
        )
    )
    # Set params
    ssh_key_file = module.params.get('path')
    ssh_key_name = module.params.get('name')
    key_state = module.params.get('state')
    ovh_endpoint = module.params.get('region')
    ssh_key = None

    client = ovh.Client(endpoint=ovh_endpoint)
    if key_state == "present":
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
            module.fail_json(msg='Unknow error')
        to_change = get_and_compare(module, client, ssh_key_name, ssh_key)
        if to_change == "Ok":
            module.exit_json(changed=False)

        if to_change == "ToUpdate":
            try:
                client.delete('/me/sshKey/{}'.format(ssh_key_name))
            except:
                e = sys.exc_info()[0]
                module.fail_json(msg='delete failed {}'.format(e))
            to_change = "NotExists"
        if to_change == "NotExists":
            try:
                client.post("/me/sshKey", key=ssh_key, keyName=ssh_key_name)
            except:
                e = sys.exc_info()[0]
                module.fail_json(msg='post fail {}'.format(e))
            module.exit_json(changed=True)
    if key_state == "absent":
        try:
            client.get('/me/sshKey/{}'.format(ssh_key_name))
        except ovh.ResourceNotFoundError:
            module.exit_json(changed=False)
        except:
            e = sys.exc_info()[0]
            module.fail_json(msg="Unknown API Error: ' {}".format(e))
        try:
            client.delete('/me/sshKey/{}'.format(ssh_key_name))
        except:
            e = sys.exc_info()[0]
            module.fail_json(msg='delete fail {}'.format(e))
        module.exit_json(changed=True)

    module.fail_json(msg="you shouln't be here !")

# import module snippets
from ansible.module_utils.basic import *
main()