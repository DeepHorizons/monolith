#! /usr/bin/env python
"""
Look at a docker image and make a singularity image that uses it with the proper envs
"""

import re
import json
import argparse
import subprocess
import shlex
import inspect
import os
import requests as r
import image_types

DOCKER_REGISTRY_URL = 'https://registry.hub.docker.com/v2/'


def gen_scope(name):
    """
    Generate a scope string to use
    Follow
    https://docs.docker.com/registry/spec/auth/token/#how-to-authenticate
    """
    return "&scope=repository:{name}:pull".format(name=name)

def docker_env_to_singularity(env):
    """
    Given a Docker ENV entry in the form of 

    NAME=VALUE

    Get the string that will be used in singularity
    """
    name, value = re.search(r'(.*?)=(.*)', env).groups()  # Don't need this, but it may be helpful in the future
    string =  """echo 'export {env}' >> $SINGULARITY_ENVIRONMENT
    export {env}""".format(env=env)
    return string


def get_docker_image_history(image_name):
    print('Processing: ' + image_name)
    image = image_types.DockerImage(image_name)
    print("Got User: {user}; Image: {image}; Ref: {ref}".format(user=image.get_docker_info().user, image=image.get_docker_info().image, ref=image.get_docker_info().ref))

    print("Getting auth token for docker registry")
    # Get the OAuth token from docker
    # https://docs.docker.com/registry/spec/auth/token/#how-to-authenticate
    auth_url, service = re.search(r'realm="(.*)",service="(.*)"', r.get(DOCKER_REGISTRY_URL).headers['Www-Authenticate']).groups()
    token = r.get(auth_url + "?service={service}".format(service=service) + gen_scope(image.gen_name())).json()['token']
    headers = {'Authorization': 'Bearer {token}'.format(token=token),
               'Accept': 'application/vnd.docker.distribution.manifest.list.v2+json'}
    headers_v2 = {'Authorization': 'Bearer {token}'.format(token=token),
               'Accept': 'application/vnd.docker.distribution.manifest.v2+json'}

    # XXX The docker registry doesnt give back history if given a digest (ie. sha256:blah)
    url = '{name}/manifests/{ref}'.format(name=image.gen_name(), ref=image.get_docker_info().ref)
    print("Looking up: " + url)
    resp = r.get(DOCKER_REGISTRY_URL + url, headers=headers)
    image_manifest = resp.json()
    image_history = image_manifest['history']
    top = json.loads(image_history[0]['v1Compatibility'])
    env = top['config']['Env']

    # Get the image digest, need to use the v2 manifest to get the correct hash
    resp = r.head(DOCKER_REGISTRY_URL + url, headers=headers_v2)
    digest = resp.headers['Docker-Content-Digest']

    full_image_name = image.gen_name() + '@{digest}'.format(digest=digest)
    envs = '\n    '.join(docker_env_to_singularity(i) for i in env)

    # Get all the history for this image
    # It is in reverse order, ie. 0 is the last command
    history = [' '.join(json.loads(i['v1Compatibility'])['container_config']['Cmd']) for i in image_history]
    return history


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Generate a singularity definition file from a docker image")
    parser.add_argument('-f', '--file', type=str, help="Where to write the file out to", default='Singularity')
    parser.add_argument('image_name', type=str, help="The name of the image, as such: 'nvidia/cuda:8.0-cudnn5-devel'. We don't support digests at this time")
    args = parser.parse_args()

    history = get_docker_image_history(args.image_name)
    
    # Get the ENTRYPOINT
    entrypoints = [i for i in history if 'ENTRYPOINT' in i]  # TODO is ENTRYPOINT always in caps?
    entrypoint = entrypoints.pop(0) if len(entrypoints) > 0 else ''
    if len(entrypoints) > 0:
        entrypoint = entrypoints.pop(0)  # Grab the first entry
        # Do some string manipulation to see what we need to do
        entrypoint = entrypoint[entrypoint.find('ENTRYPOINT')+3:].strip()
        if entrypoint.startswith('['):
            entrypoint = ' '.join(re.findall(r'\[(.*)\]', cmd))  # Get everything in the brackets
            entrypoint = ' '.join(cmd.replace('"', '').split(','))  # Flaten out the string
        # If it's not in list form, don't do anything
    else:
        entrypoint = ''

    cmds = [i for i in history if 'CMD' in i]  # TODO is CMD always in caps?
    if len(cmds) > 0:
        cmd = cmds.pop(0)  # Grab the first entry
        # Do some string manipulation to see what we need to do
        cmd = cmd[cmd.find('CMD')+3:].strip()
        if cmd.startswith('['):
            cmd = ' '.join(re.findall(r'\[(.*)\]', cmd))  # Get everything in the brackets
            cmd = ' '.join(cmd.replace('"', '').split(','))  # Flaten out the string
        # If it's not in list form, don't do anything
    else:
        cmd = ''

    singularity_file = FILE_TEMPLATE.format(IMAGE=full_image_name, ENVS=envs, ENTRYPOINT=entrypoint, CMD=cmd)
    
    with open(args.file, 'w') as f:
        f.write(singularity_file)

