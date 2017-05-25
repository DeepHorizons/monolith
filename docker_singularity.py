#! /usr/bin/env python
"""
Look at a docker image and make a singularity image that uses it with the proper envs
"""

import requests as r
import re
import json
import argparse

DOCKER_REGISTRY_URL = 'https://registry.hub.docker.com/v2/'

# TODO get the proper runscript
FILE_TEMPLATE = """
BootStrap: docker
From: {IMAGE}

%post
    # commands to be executed inside container during bootstrap

    {ENVS}


%runscript
    # commands to be executed when the container runs
    if [ -z "$1" ]
    then
        exec bash
    else
        exec "$@"
    fi

"""

class Image(object):
    def __init__(self, name):
        """
        Given a name of the form
       
        user/image:tag
        user/image
        image
        image:tag
        image@sha256:digest
        user/image@sha256:digest

        make an object that represents it
        """
        # Get everything in the form given in the docstring. Include characters, digits, and '-'
        # Note that the ref needs the `sha256:` bit, so it also needs the `:` in the capture group
        regex = r"\A(?:([\w\-\d\.]+)\/)?([\w\-\d\.]+)(?:(?::|@)([:\w\-\d\.]+))?\Z"

        # Get the values, set default ones if need be
        self.user, self.image, self.ref = re.match(regex, name).groups()
        if self.user is None:
            self.user = 'library'
        if self.ref is None:
            self.ref = 'latest'

    def gen_name(self):
        """
        Generate the string that docker expects as the "name",
        or "user/image"
        """
        return "{user}/{image}".format(user=self.user, image=self.image)


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
    string =  "echo 'export {env}' >> /environment".format(env=env)
    return string



if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Generate a singularity definition file from a docker image")
    parser.add_argument('-f', '--file', type=str, help="Where to write the file out to", default='Singularity')
    parser.add_argument('image_name', type=str, help="The name of the image, as such: 'nvidia/cuda:8.0-cudnn5-devel'. We don't support digests at this time")
    args = parser.parse_args()

    print('Processing: ' + args.image_name)
    image = Image(args.image_name)
    print("Got User: {user}; Image: {image}; Ref: {ref}".format(user=image.user, image=image.image, ref=image.ref))

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
    url = '{name}/manifests/{ref}'.format(name=image.gen_name(), ref=image.ref)
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
    envs = "echo '\\n' >> /environment\n    " + '\n    '.join(docker_env_to_singularity(i) for i in env)

    singularity_file = FILE_TEMPLATE.format(IMAGE=full_image_name, ENVS=envs)
    
    with open(args.file, 'w') as f:
        f.write(singularity_file)

