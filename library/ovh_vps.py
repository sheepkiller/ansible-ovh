#!/usr/bin/env python

# ovh_ssh: manage your ovh ssh keys
# inspired by https://github.com/gheesh/ansible-ovh-dns/

DOCUMENTATION = '''
---
module: ovh_vps
author: Clement Laforet
short_description: Manipulate OVH vps
description:
    - Manage OVH VPS (2014/2016)
#!/usr/bin/env python

requirements: [ "ovh" ]
options:
    name:
        required: true
        description:
            - service name (aka ovh_name) of the VPS
    action:
    template:
        require: false
        description:
            - reinstall action only. templateid (from /vps/template)
    ssh_key:
        require: false
        description:
            - reinstall action only. sshkey (from /me/sshKeys)
'''

EXAMPLES = '''
# reboot a vps
ovh_vps: name="vps00000.ovh.net" action=reboot
# stop vps
ovh_vps: name="vps00000.ovh.net" action=stop
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


def get_ovh_endpoints():
    lep = []
    for ep in ovh.client.ENDPOINTS:
        lep.append(ep)
    return lep


def get_vps_info(module, client, name):
    resp = None
    try:
        resp = client.get('/vps/{}'.format(name))
    except:
        e = sys.exc_info()[0]
        module.fail_json(msg="Unable to get status. Unknown API Error: ' {}".format(e))
    return resp


def main():
    module = AnsibleModule(
        argument_spec=dict(
            state=dict(default='running'),
            name=dict(require=True),
            action=dict(default=None, choices=[
                                    None,
                                    "reboot",
                                    "reinstall",
                                    "stop",
                                    "start"]),
            template=dict(default=None),
            language=dict(default='en'),
            ssh_key=dict(default=None),
            region=dict(default='ovh-eu', choices=get_ovh_endpoints())
        )
    )

    # get parameters
    name = module.params.get('name')
    action = module.params.get('action')
    templateid = module.params.get('template')
    ssh_key = module.params.get('ssh_key')
    language = module.params.get('language')


    client = ovh.Client()
    vps = get_vps_info(module, client, name)

    if action == 'reboot':
        if vps["state"] != "running":
            module.exit_json(
                msg="VPS state must be running, not {}".format(vps["state"]),
                changed=False)
        resp = None
        try:
            resp = client.post('/vps/{}/reboot'.format(name))
        except:
            e = sys.exc_info()[0]
            module.fail_json(msg="reboot Unknown API Error: ' {}".format(e))
        module.exit_json(changed=True)

    if action == 'start':
        if vps["state"] != "stopped":
            module.exit_json(
                msg="VPS state must be stopped not {}".format(vps["state"]),
                changed=False)
        resp = None
        try:
            resp = client.post('/vps/{}/start'.format(name))
        except:
            e = sys.exc_info()[0]
            module.fail_json(msg="start Unknown API Error: ' {}".format(e))
        module.exit_json(changed=True)

    if action == 'stop':
        if vps["state"] != "running":
            module.exit_json(
                msg="VPS state must be running not {}".format(vps["state"]),
                changed=False)
        resp = None
        try:
            resp = client.post('/vps/{}/stop'.format(name))
        except:
            e = sys.exc_info()[0]
            module.fail_json(msg="stop: Unknown API Error: ' {}".format(e))
        module.exit_json(changed=True)

    if action == 'reinstall':
        resp = None
        # tested only when VPS is running
        if vps["state"] != "running":
            module.fail_json(msg='not tested on a not running VPS')
        if ssh_key == None:
            module.fail_json(msg='you must defined a ssh key')
        try:
            resp = client.post('/vps/{}/reinstall'.format(name),
                            language=language,
                            templateId=long(templateid),
                            sshKey=ssh_key.split(" "))
        except:
            e = sys.exc_info()[0]
            module.fail_json(msg="reinstall: Unknown API Error: ' {}".format(e))
        module.exit_json(changed=True)

    module.exit_json(changed=False)


# import module snippets
from ansible.module_utils.basic import *
main()
