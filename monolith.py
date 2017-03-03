#! /usr/bin/env python
"""
Make a monolithic dockerfile from a given image name
"""
import requests
from bs4 import BeautifulSoup
import re
import datetime
import argparse

BASE_URL = "https://hub.docker.com/r/{user}/{image}/"
DOCKERFILE_URL = BASE_URL + "~/dockerfile/"

def get_dockerfile(name):
    """
       Given a name of the form
       
       user/image:tag
       user/image
       image
       image:tag
       
       Attempt to get the dockerfile and return the text
    """
    print('getting:' + name)
    # Get everything in the form given in the docstring. Include characters, digits, and '-'
    regex = r"\A(?:([\w\-\d\.]+)\/)?([\w\-\d\.]+)(?::([\w\-\d\.]+))?\Z"

    # Get the values, set default ones if need be
    user, image, tag = re.match(regex, name).groups()
    if user is None:
        user = '_'
    if tag is None:
        tag = ':latest'

    # Make a call out to get the page
    result = requests.get(DOCKERFILE_URL.format(user=user, image=image))
    # Make sure we got a page, dockerhub does not return a 404 if the page does not exist
    if 'RouteNotFound404Page' in result.content.decode():
        print('Unable to get dockerfile from {}'.format(name))
        return ''

    # Parse it, get the span that has the dockerfile text
    soup = BeautifulSoup(result.content, "html.parser")
    html = soup.select('span[class*="Dockerfile"]')[0]
    # Return the text
    return html.text if html.text else ''

def get_from(dockerfile):
    """
       Given the text of a dockerfile, see where it was derived from
    """
    # Look for the string `FROM` that is not prefaced with a comment
    regex = r'^(?:(?!#).)*(?:FROM|from)\s+(\S+)'
    return re.search(regex, dockerfile, re.MULTILINE).groups()[0]

def get_tree(name):
    """
       Given an image name, get all the docker files that were used up to the root node
    """
    dockerfile = get_dockerfile(name)
    # Set a header so we know where the commands are comming from
    # TODO get hash
    s = "### {} --- {}\n".format(name, str(datetime.datetime.now()))
    s += dockerfile
    # If there was a dockerfile, find out where it came from and append that
    if dockerfile:
        name = get_from(dockerfile)
        return get_tree(name) + s
    return s

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Make a monolithic Dockerfile")
    parser.add_argument('-f', '--file', type=str, help="Where to write the file out to", default='Monolith.txt')
    parser.add_argument('image_name', type=str, help="The name of the image, as such: 'jupyterhub/jupyterhub'")
    args = parser.parse_args()

    monolith = get_tree(args.image_name)
    with open(args.file, 'w') as f:
        f.write(monolith)

